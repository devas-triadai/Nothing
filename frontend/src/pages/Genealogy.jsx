import { useState, useEffect, useRef, useCallback } from 'react'
import { apiFetch } from '../utils/api'
import { Network, Search, Filter, Maximize2, GitBranch, ArrowLeft, RefreshCw, ZoomIn, ZoomOut, Download, Link2, Calendar, FileText, GitCompare, X, ChevronDown, Check, CheckCircle } from 'lucide-react'
import * as d3 from 'd3'

// ── Theme / Colors ──
const CAT_COLORS = {
  'SOP': '#10b981',
  'Standard': '#3b82f6',
  'SOTR': '#8b5cf6',
  'Blueprint': '#ec4899',
  'Report': '#f59e0b',
  'Compliance': '#ef4444',
  'Bid Document': '#06b6d4',
  'IMO Standard': '#6366f1',
  'ICG Document': '#0ea5e9',
  'Vessel Document': '#14b8a6',
  'General': '#6b7280',
}

const EDGE_TYPES = [
  { key: 'supersedes', label: 'SUPERSEDES', color: '#ef4444', desc: 'Replaces previous version' },
  { key: 'derived_from', label: 'DERIVED FROM', color: '#3b82f6', desc: 'Substantially based on' },
  { key: 'informed_by', label: 'INFORMED BY', color: '#8b5cf6', desc: 'Influenced by' },
  { key: 'references', label: 'REFERENCES', color: '#f59e0b', desc: 'Cites or cites normatively' },
  { key: 'amends', label: 'AMENDS', color: '#10b981', desc: 'Formal amendment to' },
]

export default function Genealogy() {
  const [nodes, setNodes] = useState([])
  const [edges, setEdges] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedNode, setSelectedNode] = useState(null)
  
  // View mode
  const [viewMode, setViewMode] = useState('graph') // 'graph' | 'timeline'
  
  // Filters
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategories, setSelectedCategories] = useState([])
  const [selectedEdgeTypes, setSelectedEdgeTypes] = useState([])
  const [showFilters, setShowFilters] = useState(false)
  
  // Modals
  const [showLinkModal, setShowLinkModal] = useState(false)
  const [showDiffModal, setShowDiffModal] = useState(false)
  const [linkTargetId, setLinkTargetId] = useState('')
  const [linkEdgeType, setLinkEdgeType] = useState('references')
  const [linkConfidence, setLinkConfidence] = useState(1.0)
  const [allDocs, setAllDocs] = useState([])
  
  const svgRef = useRef(null)
  const containerRef = useRef(null)
  const simulationRef = useRef(null)
  const zoomRef = useRef(null)

  useEffect(() => {
    fetchGraphData()
  }, [])

  async function fetchGraphData() {
    setLoading(true)
    try {
      const [lineageData, docsData] = await Promise.all([
        apiFetch('/documents/lineage/all'),
        apiFetch('/documents/?limit=1000')
      ])
      if (lineageData && lineageData.nodes) {
        setNodes(lineageData.nodes)
        setEdges(lineageData.edges)
      }
      if (docsData && docsData.documents) {
        setAllDocs(docsData.documents)
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  // Filtered data based on search and filters
  const filteredNodes = nodes.filter(n => {
    const matchesSearch = !searchQuery || 
      (n.filename && n.filename.toLowerCase().includes(searchQuery.toLowerCase())) ||
      (n.category && n.category.toLowerCase().includes(searchQuery.toLowerCase()))
    const matchesCategory = selectedCategories.length === 0 || selectedCategories.includes(n.category)
    return matchesSearch && matchesCategory
  })

  const filteredEdges = edges.filter(e => {
    const sourceInNodes = filteredNodes.some(n => n.id === e.source || n.id === e.source?.id)
    const targetInNodes = filteredNodes.some(n => n.id === e.target || n.id === e.target?.id)
    const matchesType = selectedEdgeTypes.length === 0 || selectedEdgeTypes.includes(e.type)
    return sourceInNodes && targetInNodes && matchesType
  })

  // ── D3 Force-Directed Graph ──
  useEffect(() => {
    if (loading || !nodes.length || !svgRef.current || viewMode !== 'graph') return

    const width = containerRef.current.clientWidth
    const height = containerRef.current.clientHeight

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    if (filteredNodes.length === 0) return

    // Add defs section for arrowheads with different colors
    const defs = svg.append('defs')
    
    EDGE_TYPES.forEach(edgeType => {
      defs.append('marker')
        .attr('id', `arrow-${edgeType.key}`)
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 22)
        .attr('refY', 0)
        .attr('markerWidth', 6)
        .attr('markerHeight', 6)
        .attr('orient', 'auto')
        .append('path')
        .attr('fill', edgeType.color)
        .attr('d', 'M0,-5L10,0L0,5')
    })
    
    // Default arrow
    defs.append('marker')
      .attr('id', 'arrow-default')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 22)
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('fill', '#94a3b8')
      .attr('d', 'M0,-5L10,0L0,5')

    const g = svg.append('g')

    // Zoom behavior
    const zoom = d3.zoom()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => g.attr('transform', event.transform))
    
    svg.call(zoom)
    zoomRef.current = zoom

    // Prepare data for D3
    const graphNodes = filteredNodes.map(n => ({ ...n, radius: 16 }))
    
    // Edges need direct references to nodes array
    const graphEdges = filteredEdges.map(e => {
      const sourceNode = graphNodes.find(n => n.id === (e.source?.id || e.source))
      const targetNode = graphNodes.find(n => n.id === (e.target?.id || e.target))
      return {
        source: sourceNode || e.source,
        target: targetNode || e.target,
        type: e.type || 'references'
      }
    }).filter(e => e.source && e.target && typeof e.source === 'object' && typeof e.target === 'object')

    // Simulation
    const simulation = d3.forceSimulation(graphNodes)
      .force('link', d3.forceLink(graphEdges).id(d => d.id).distance(120))
      .force('charge', d3.forceManyBody().strength(-400))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collide', d3.forceCollide().radius(35))

    simulationRef.current = simulation

    // Draw Links with edge type colors
    const link = g.append('g')
      .selectAll('line')
      .data(graphEdges)
      .join('line')
      .attr('stroke', d => {
        const edgeType = EDGE_TYPES.find(et => et.key === d.type)
        return edgeType ? edgeType.color : '#94a3b8'
      })
      .attr('stroke-width', 2)
      .attr('stroke-opacity', 0.7)
      .attr('marker-end', d => {
        const edgeType = EDGE_TYPES.find(et => et.key === d.type)
        return `url(#arrow-${edgeType ? edgeType.key : 'default'})`
      })

    // Draw Nodes
    const node = g.append('g')
      .selectAll('g')
      .data(graphNodes)
      .join('g')
      .attr('cursor', 'pointer')
      .call(drag(simulation))
      .on('click', (event, d) => {
        setSelectedNode(d)
        event.stopPropagation()
      })

    // Node circles
    node.append('circle')
      .attr('r', d => d.radius)
      .attr('fill', d => CAT_COLORS[d.category] || CAT_COLORS['General'])
      .attr('stroke', 'var(--bg-card)')
      .attr('stroke-width', 3)
      .style('filter', 'drop-shadow(0 4px 6px rgba(0,0,0,0.3))')

    // Node labels
    node.append('text')
      .text(d => d.filename.length > 20 ? d.filename.slice(0, 20) + '...' : d.filename)
      .attr('x', 22)
      .attr('y', 4)
      .style('font-size', '12px')
      .style('font-family', 'var(--font-sans)')
      .style('fill', 'var(--text-primary)')
      .style('pointer-events', 'none')

    // Version badge
    node.append('text')
      .text(d => `v${d.version || 1}`)
      .attr('x', -25)
      .attr('y', -20)
      .style('font-size', '10px')
      .style('font-weight', 'bold')
      .style('fill', 'var(--text-secondary)')

    svg.on('click', () => setSelectedNode(null))

    simulation.on('tick', () => {
      link
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y)

      node
        .attr('transform', d => `translate(${d.x},${d.y})`)
    })

    return () => simulation.stop()
  }, [filteredNodes, filteredEdges, loading, viewMode])

  // ── Export Functions ──
  const handleExport = async (format) => {
    try {
      const data = await apiFetch(`/documents/lineage/export?format=${format}`)
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `agra-lineage.${format === 'json-ld' ? 'json' : 'graphml'}`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      console.error('Export failed:', e)
      alert('Export failed. Please try again.')
    }
  }

  // ── Create Manual Link ──
  const handleCreateLink = async () => {
    if (!selectedNode || !linkTargetId) return
    try {
      await apiFetch(`/documents/${selectedNode.id}/link`, {
        method: 'POST',
        body: JSON.stringify({
          target_id: parseInt(linkTargetId),
          edge_type: linkEdgeType,
          confidence: linkConfidence
        })
      })
      setShowLinkModal(false)
      setLinkTargetId('')
      setLinkEdgeType('references')
      setLinkConfidence(1.0)
      fetchGraphData()
    } catch (e) {
      console.error('Link creation failed:', e)
      alert('Failed to create link. Please try again.')
    }
  }

  // ── Timeline View Data ──
  const timelineData = filteredNodes
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
    .reduce((acc, doc) => {
      const group = doc.group || doc.id
      if (!acc[group]) acc[group] = []
      acc[group].push(doc)
      return acc
    }, {})

  // Drag utility for D3
  function drag(simulation) {
    function dragstarted(event) {
      if (!event.active) simulation.alphaTarget(0.3).restart();
      event.subject.fx = event.subject.x;
      event.subject.fy = event.subject.y;
    }
    function dragged(event) {
      event.subject.fx = event.x;
      event.subject.fy = event.y;
    }
    function dragended(event) {
      if (!event.active) simulation.alphaTarget(0);
      event.subject.fx = null;
      event.subject.fy = null;
    }
    return d3.drag()
      .on("start", dragstarted)
      .on("drag", dragged)
      .on("end", dragended);
  }

  const handleZoom = (factor) => {
    if (!svgRef.current || !zoomRef.current) return
    d3.select(svgRef.current).transition().duration(300).call(zoomRef.current.scaleBy, factor)
  }

  const handleResetZoom = () => {
    if (!svgRef.current || !zoomRef.current) return
    d3.select(svgRef.current).transition().duration(500)
      .call(zoomRef.current.transform, d3.zoomIdentity)
  }

  const toggleCategory = (cat) => {
    setSelectedCategories(prev => 
      prev.includes(cat) ? prev.filter(c => c !== cat) : [...prev, cat]
    )
  }

  const toggleEdgeType = (type) => {
    setSelectedEdgeTypes(prev => 
      prev.includes(type) ? prev.filter(t => t !== type) : [...prev, type]
    )
  }

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1600, margin: '0 auto', height: 'calc(100vh - 80px)', display: 'flex', flexDirection: 'column' }}>
      {/* Header with Toolbar */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 20 }}>
        {/* Title Row */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-heading)', margin: 0, display: 'flex', alignItems: 'center', gap: 10 }}>
              <Network size={24} color="#8b5cf6" />
              Document Genealogy
            </h1>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '4px 0 0' }}>
              Interactive DAG visualization with lineage tracking and version control
            </p>
          </div>
          
          <div style={{ display: 'flex', gap: 10 }}>
            <button onClick={() => handleExport('json-ld')} title="Export JSON-LD"
              style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--card-bg)', color: 'var(--text-secondary)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
              <Download size={14} /> JSON-LD
            </button>
            <button onClick={() => handleExport('graphml')} title="Export GraphML"
              style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--card-bg)', color: 'var(--text-secondary)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
              <Download size={14} /> GraphML
            </button>
            <button onClick={fetchGraphData} title="Refresh"
              style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--card-bg)', color: 'var(--text-secondary)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
              <RefreshCw size={14} />
            </button>
          </div>
        </div>

        {/* Toolbar Row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          {/* Search */}
          <div style={{ position: 'relative', flex: 1, minWidth: 200, maxWidth: 300 }}>
            <Search size={16} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
            <input 
              type="text" 
              placeholder="Search documents..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ width: '100%', padding: '10px 12px 10px 36px', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--card-bg)', color: 'var(--text-primary)', fontSize: 14 }}
            />
          </div>

          {/* View Mode Toggle */}
          <div style={{ display: 'flex', border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden' }}>
            <button 
              onClick={() => setViewMode('graph')}
              style={{ padding: '10px 16px', background: viewMode === 'graph' ? 'var(--primary)' : 'var(--card-bg)', color: viewMode === 'graph' ? 'white' : 'var(--text-secondary)', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}
            >
              <Network size={16} /> Graph
            </button>
            <button 
              onClick={() => setViewMode('timeline')}
              style={{ padding: '10px 16px', background: viewMode === 'timeline' ? 'var(--primary)' : 'var(--card-bg)', color: viewMode === 'timeline' ? 'white' : 'var(--text-secondary)', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}
            >
              <Calendar size={16} /> Timeline
            </button>
          </div>

          {/* Filter Toggle */}
          <button 
            onClick={() => setShowFilters(!showFilters)}
            style={{ padding: '10px 16px', borderRadius: 8, border: '1px solid var(--border)', background: showFilters ? 'var(--primary)' : 'var(--card-bg)', color: showFilters ? 'white' : 'var(--text-secondary)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}
          >
            <Filter size={16} /> Filters
            {(selectedCategories.length > 0 || selectedEdgeTypes.length > 0) && (
              <span style={{ background: 'rgba(255,255,255,0.3)', padding: '2px 6px', borderRadius: 10, fontSize: 11 }}>
                {selectedCategories.length + selectedEdgeTypes.length}
              </span>
            )}
          </button>
        </div>

        {/* Filter Panel */}
        {showFilters && (
          <div style={{ display: 'flex', gap: 24, padding: 16, background: 'var(--card-bg)', borderRadius: 12, border: '1px solid var(--border)' }}>
            {/* Category Filter */}
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 10 }}>Categories</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {Object.keys(CAT_COLORS).map(cat => (
                  <button
                    key={cat}
                    onClick={() => toggleCategory(cat)}
                    style={{ 
                      padding: '6px 12px', borderRadius: 6, border: '1px solid var(--border)',
                      background: selectedCategories.includes(cat) ? `${CAT_COLORS[cat]}20` : 'var(--bg-surface)',
                      color: selectedCategories.includes(cat) ? CAT_COLORS[cat] : 'var(--text-secondary)',
                      cursor: 'pointer', fontSize: 12, display: 'flex', alignItems: 'center', gap: 6
                    }}
                  >
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: CAT_COLORS[cat] }} />
                    {cat}
                    {selectedCategories.includes(cat) && <Check size={12} />}
                  </button>
                ))}
              </div>
            </div>

            {/* Edge Type Filter */}
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 10 }}>Relationship Types</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {EDGE_TYPES.map(et => (
                  <button
                    key={et.key}
                    onClick={() => toggleEdgeType(et.key)}
                    style={{ 
                      padding: '6px 12px', borderRadius: 6, border: '1px solid var(--border)',
                      background: selectedEdgeTypes.includes(et.key) ? `${et.color}20` : 'var(--bg-surface)',
                      color: selectedEdgeTypes.includes(et.key) ? et.color : 'var(--text-secondary)',
                      cursor: 'pointer', fontSize: 12, display: 'flex', alignItems: 'center', gap: 6
                    }}
                  >
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: et.color }} />
                    {et.label}
                    {selectedEdgeTypes.includes(et.key) && <Check size={12} />}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Main Content Area */}
      <div style={{ display: 'flex', gap: 20, flex: 1, minHeight: 0 }}>
        
        {/* Graph/Timeline Container */}
        <div 
          ref={containerRef}
          style={{ 
            flex: 1, background: 'var(--card-bg)', borderRadius: 16, border: '1px solid var(--border)', 
            position: 'relative', overflow: 'hidden', boxShadow: 'inset 0 0 40px rgba(0,0,0,0.04)'
          }}
        >
          {loading && (
            <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,0.05)', zIndex: 10 }}>
              <span style={{ color: 'var(--text-secondary)' }}>Loading genealogy data...</span>
            </div>
          )}

          {/* GRAPH VIEW */}
          {viewMode === 'graph' && (
            <>
              {/* Zoom Controls */}
              <div style={{ position: 'absolute', bottom: 20, right: 20, display: 'flex', flexDirection: 'column', gap: 8, zIndex: 10 }}>
                <button onClick={() => handleZoom(1.2)} style={zoomBtnStyle}><ZoomIn size={16} /></button>
                <button onClick={() => handleResetZoom()} style={zoomBtnStyle}><Maximize2 size={16} /></button>
                <button onClick={() => handleZoom(0.8)} style={zoomBtnStyle}><ZoomOut size={16} /></button>
              </div>

              {/* Legend */}
              <div style={{ position: 'absolute', top: 20, left: 20, background: 'var(--card-bg)', padding: 16, borderRadius: 12, border: '1px solid var(--border)', boxShadow: 'var(--shadow-sm)', zIndex: 10, maxHeight: '60%', overflowY: 'auto' }}>
                <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 12 }}>Categories</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 20 }}>
                  {Object.entries(CAT_COLORS).map(([cat, color]) => (
                    <div key={cat} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ width: 10, height: 10, borderRadius: '50%', background: color }} />
                      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{cat}</span>
                    </div>
                  ))}
                </div>
                
                <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 12, marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--border)' }}>Relationships</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {EDGE_TYPES.map(et => (
                    <div key={et.key} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ width: 20, height: 2, background: et.color, borderRadius: 1 }} />
                      <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{et.label}</span>
                    </div>
                  ))}
                </div>
              </div>

              <svg ref={svgRef} style={{ width: '100%', height: '100%', display: 'block' }} />
            </>
          )}

          {/* TIMELINE VIEW */}
          {viewMode === 'timeline' && (
            <div style={{ width: '100%', height: '100%', overflow: 'auto', padding: 24 }}>
              {Object.keys(timelineData).length === 0 ? (
                <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-muted)' }}>
                  No documents to display. Try adjusting filters.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
                  {Object.entries(timelineData).map(([groupId, docs]) => (
                    <div key={groupId} style={{ borderLeft: '3px solid var(--border)', paddingLeft: 24 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                        <GitBranch size={20} color="var(--text-muted)" />
                        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-heading)' }}>
                          {docs[0]?.filename?.split('.')[0] || 'Document Group'}
                        </span>
                        <span style={{ fontSize: 12, color: 'var(--text-muted)', background: 'var(--bg-surface)', padding: '4px 8px', borderRadius: 6 }}>
                          {docs.length} version{docs.length > 1 ? 's' : ''}
                        </span>
                      </div>
                      
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                        {docs.map((doc, idx) => (
                          <div 
                            key={doc.id}
                            onClick={() => setSelectedNode(doc)}
                            style={{ 
                              display: 'flex', alignItems: 'center', gap: 16, padding: 16, 
                              background: 'var(--bg-surface)', borderRadius: 12, border: '1px solid var(--border)',
                              cursor: 'pointer', transition: 'all 0.2s'
                            }}
                          >
                            <div style={{ 
                              width: 40, height: 40, borderRadius: '50%', 
                              background: `${CAT_COLORS[doc.category] || CAT_COLORS['General']}20`,
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
                              border: `2px solid ${CAT_COLORS[doc.category] || CAT_COLORS['General']}`
                            }}>
                              <span style={{ fontSize: 12, fontWeight: 700, color: CAT_COLORS[doc.category] || CAT_COLORS['General'] }}>
                                v{doc.version}
                              </span>
                            </div>
                            
                            <div style={{ flex: 1 }}>
                              <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4 }}>
                                {doc.filename}
                              </div>
                              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                                {doc.category} • {new Date(doc.created_at).toLocaleDateString()} • {doc.status}
                              </div>
                            </div>
                            
                            {doc.version_notes && (
                              <div style={{ maxWidth: 300, fontSize: 12, color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                                "{doc.version_notes}"
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Info Panel */}
        {selectedNode && (
          <div style={{ 
            width: 340, background: 'var(--card-bg)', borderRadius: 16, border: '1px solid var(--border)',
            padding: 24, display: 'flex', flexDirection: 'column', overflowY: 'auto'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
              <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 10px', borderRadius: 8, fontSize: 11, fontWeight: 700, background: `${CAT_COLORS[selectedNode.category] || CAT_COLORS['General']}20`, color: CAT_COLORS[selectedNode.category] || CAT_COLORS['General'] }}>
                {selectedNode.category || 'General'}
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 600 }}>v{selectedNode.version || 1}</span>
                <button onClick={() => setSelectedNode(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 0 }}>
                  <X size={18} />
                </button>
              </div>
            </div>
            
            <h3 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-heading)', margin: '0 0 16px 0', wordBreak: 'break-word' }}>
              {selectedNode.original_filename || selectedNode.filename}
            </h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 24 }}>
              <DetailRow label="Source" value={selectedNode.source || 'Unknown'} />
              <DetailRow label="Status" value={selectedNode.status} capitalize />
              <DetailRow label="File Size" value={selectedNode.file_size ? `${(selectedNode.file_size / 1024).toFixed(0)} KB` : 'N/A'} />
              <DetailRow label="Confidence" value={selectedNode.classification_confidence ? `${Math.round(selectedNode.classification_confidence * 100)}%` : 'N/A'} />
              <DetailRow label="Uploaded" value={selectedNode.created_at ? new Date(selectedNode.created_at).toLocaleDateString() : 'N/A'} />
            </div>

            {selectedNode.version_notes && (
              <div style={{ background: 'var(--bg-surface)', padding: 14, borderRadius: 10, border: '1px solid var(--border)', marginBottom: 20 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 6 }}>Version Notes</div>
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>{selectedNode.version_notes}</div>
              </div>
            )}

            {/* Action Buttons */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 20 }}>
              <button 
                onClick={() => setShowLinkModal(true)}
                style={{ padding: '10px 14px', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--bg-surface)', color: 'var(--text-primary)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, fontSize: 13 }}
              >
                <Link2 size={16} /> Create Relationship
              </button>
              <button 
                onClick={() => setShowDiffModal(true)}
                style={{ padding: '10px 14px', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--bg-surface)', color: 'var(--text-primary)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, fontSize: 13 }}
              >
                <GitCompare size={16} /> Compare with Previous
              </button>
            </div>

            <div style={{ marginTop: 'auto', paddingTop: 20, borderTop: '1px solid var(--border)' }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 12 }}>Lineage Info</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                <strong>Group ID:</strong> {selectedNode.doc_group_id ? selectedNode.doc_group_id.slice(0, 8) + '...' : 'None'}<br/>
                <strong>Parent ID:</strong> {selectedNode.parent_doc_id || 'Root Document'}<br/>
                <strong>SHA-256:</strong> {selectedNode.sha256_hash ? selectedNode.sha256_hash.slice(0, 12) + '...' : 'N/A'}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Create Relationship Modal */}
      {showLinkModal && selectedNode && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
          <div style={{ width: 480, background: 'var(--card-bg)', borderRadius: 16, border: '1px solid var(--border)', padding: 24 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h3 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-heading)', margin: 0 }}>Create Relationship</h3>
              <button onClick={() => setShowLinkModal(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
                <X size={20} />
              </button>
            </div>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div>
                <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6, display: 'block' }}>Source Document</label>
                <div style={{ padding: 12, background: 'var(--bg-surface)', borderRadius: 8, border: '1px solid var(--border)', fontSize: 14 }}>
                  {selectedNode.filename} (v{selectedNode.version})
                </div>
              </div>
              
              <div>
                <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6, display: 'block' }}>Target Document *</label>
                <select 
                  value={linkTargetId} 
                  onChange={(e) => setLinkTargetId(e.target.value)}
                  style={{ width: '100%', padding: 12, borderRadius: 8, border: '1px solid var(--border)', background: 'var(--card-bg)', color: 'var(--text-primary)', fontSize: 14 }}
                >
                  <option value="">Select document...</option>
                  {allDocs.filter(d => d.id !== selectedNode.id).map(d => (
                    <option key={d.id} value={d.id}>{d.original_filename || d.filename} (v{d.version})</option>
                  ))}
                </select>
              </div>
              
              <div>
                <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6, display: 'block' }}>Relationship Type *</label>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {EDGE_TYPES.map(et => (
                    <button
                      key={et.key}
                      onClick={() => setLinkEdgeType(et.key)}
                      style={{ 
                        padding: '8px 14px', borderRadius: 6, border: '1px solid var(--border)',
                        background: linkEdgeType === et.key ? `${et.color}20` : 'var(--bg-surface)',
                        color: linkEdgeType === et.key ? et.color : 'var(--text-secondary)',
                        cursor: 'pointer', fontSize: 12
                      }}
                    >
                      {et.label}
                    </button>
                  ))}
                </div>
              </div>
              
              <div>
                <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6, display: 'block' }}>Confidence: {linkConfidence.toFixed(1)}</label>
                <input 
                  type="range" 
                  min="0" max="1" step="0.1"
                  value={linkConfidence}
                  onChange={(e) => setLinkConfidence(parseFloat(e.target.value))}
                  style={{ width: '100%' }}
                />
              </div>
            </div>
            
            <div style={{ display: 'flex', gap: 10, marginTop: 24 }}>
              <button 
                onClick={() => setShowLinkModal(false)}
                style={{ flex: 1, padding: 12, borderRadius: 8, border: '1px solid var(--border)', background: 'var(--bg-surface)', color: 'var(--text-primary)', cursor: 'pointer', fontSize: 14 }}
              >
                Cancel
              </button>
              <button 
                onClick={handleCreateLink}
                disabled={!linkTargetId}
                style={{ flex: 1, padding: 12, borderRadius: 8, border: 'none', background: !linkTargetId ? 'var(--text-muted)' : 'var(--primary)', color: 'white', cursor: !linkTargetId ? 'not-allowed' : 'pointer', fontSize: 14 }}
              >
                Create Link
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Diff Modal */}
      {showDiffModal && selectedNode && (
        <DiffModal
          node={selectedNode}
          onClose={() => setShowDiffModal(false)}
        />
      )}
    </div>
  )
}

function DetailRow({ label, value, capitalize }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', textTransform: capitalize ? 'capitalize' : 'none' }}>
        {value}
      </span>
    </div>
  )
}

function DiffModal({ node, onClose }) {
  const [diffData, setDiffData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (node.parent_doc_id) {
      fetchDiff()
    }
  }, [node])

  async function fetchDiff() {
    setLoading(true)
    setError(null)
    try {
      const res = await apiFetch(`/documents/${node.parent_doc_id}/diff/${node.id}`)
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `HTTP ${res.status}`)
      }
      setDiffData(await res.json())
    } catch (e) {
      setError(e.message || 'Failed to load diff')
    } finally {
      setLoading(false)
    }
  }

  function renderDiffLine(line, idx) {
    let bg = 'transparent'
    let color = 'var(--text-primary)'
    let prefix = ' '

    if (line.startsWith('+++') || line.startsWith('---')) {
      bg = 'var(--bg-surface)'
      color = 'var(--text-muted)'
      prefix = ''
    } else if (line.startsWith('+')) {
      bg = '#22c55e18'
      color = '#16a34a'
      prefix = '+'
    } else if (line.startsWith('-')) {
      bg = '#ef444418'
      color = '#dc2626'
      prefix = '-'
    } else if (line.startsWith('@@')) {
      bg = '#3b82f612'
      color = '#3b82f6'
      prefix = ''
    }

    return (
      <div key={idx} style={{ background: bg, padding: '1px 12px', fontFamily: 'monospace', fontSize: 12, lineHeight: 1.7, color, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
        {line}
      </div>
    )
  }

  const impactColors = { High: '#ef4444', Medium: '#f59e0b', Low: '#22c55e' }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{ width: 900, maxHeight: '85vh', background: 'var(--card-bg)', borderRadius: 16, border: '1px solid var(--border)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Header */}
        <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h3 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-heading)', margin: 0 }}>Version Comparison</h3>
            {diffData && (
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                v{diffData.doc1?.version || '?'} → v{diffData.doc2?.version || '?'}
              </span>
            )}
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflow: 'auto', padding: 0 }}>
          {!node.parent_doc_id ? (
            <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-muted)' }}>
              <GitCompare size={48} style={{ marginBottom: 16, opacity: 0.5 }} />
              <p style={{ margin: 0, fontSize: 14 }}>This is the root document (v1). No previous version exists for comparison.</p>
            </div>
          ) : loading ? (
            <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-muted)', fontSize: 14 }}>
              <RefreshCw size={24} style={{ marginBottom: 12, animation: 'spin 1s linear infinite' }} />
              <p style={{ margin: 0 }}>Loading diff…</p>
            </div>
          ) : error ? (
            <div style={{ textAlign: 'center', padding: 60, color: '#ef4444', fontSize: 13 }}>
              <p style={{ margin: 0 }}>⚠ {error}</p>
              <button onClick={fetchDiff} style={{ marginTop: 12, padding: '6px 14px', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--bg-surface)', color: 'var(--text-primary)', cursor: 'pointer', fontSize: 12 }}>
                Retry
              </button>
            </div>
          ) : diffData ? (
            <>
              {/* Stats bar */}
              <div style={{ padding: '10px 24px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  <strong style={{ color: 'var(--text-primary)' }}>{diffData.doc1?.filename}</strong> → <strong style={{ color: 'var(--text-primary)' }}>{diffData.doc2?.filename}</strong>
                </span>
                <div style={{ marginLeft: 'auto', display: 'flex', gap: 12 }}>
                  <span style={{ fontSize: 12, color: '#16a34a', fontWeight: 600 }}>+{diffData.stats?.additions || 0}</span>
                  <span style={{ fontSize: 12, color: '#dc2626', fontWeight: 600 }}>-{diffData.stats?.deletions || 0}</span>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{diffData.stats?.total_changes || 0} changes</span>
                </div>
              </div>

              {/* LLM Change Summary */}
              {diffData.change_summary && (
                <div style={{ padding: '12px 24px', borderBottom: '1px solid var(--border)', background: 'var(--bg-surface)' }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 8 }}>AI Change Summary</div>
                  <p style={{ margin: '0 0 8px', fontSize: 13, color: 'var(--text-primary)', lineHeight: 1.5 }}>
                    {diffData.change_summary.summary_text}
                  </p>
                  {diffData.change_summary.impact_assessment && (
                    <span style={{
                      display: 'inline-block', padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 700,
                      background: (impactColors[diffData.change_summary.impact_assessment] || '#6b7280') + '22',
                      color: impactColors[diffData.change_summary.impact_assessment] || '#6b7280',
                    }}>
                      Impact: {diffData.change_summary.impact_assessment}
                    </span>
                  )}
                  {diffData.change_summary.major_changes?.length > 0 && (
                    <div style={{ marginTop: 8 }}>
                      <div style={{ fontSize: 11, color: '#ef4444', fontWeight: 600, marginBottom: 4 }}>Major Changes:</div>
                      {diffData.change_summary.major_changes.map((c, i) => (
                        <div key={i} style={{ fontSize: 12, color: 'var(--text-primary)', paddingLeft: 12, position: 'relative', marginBottom: 2 }}>
                          <span style={{ position: 'absolute', left: 0 }}>•</span> {c}
                        </div>
                      ))}
                    </div>
                  )}
                  {diffData.change_summary.action_required && (
                    <div style={{ marginTop: 8, padding: '6px 10px', borderRadius: 4, background: '#f59e0b18', border: '1px solid #f59e0b44', fontSize: 12, color: '#92400e' }}>
                      <strong>Action Required:</strong> {diffData.change_summary.action_required}
                    </div>
                  )}
                </div>
              )}

              {/* Diff lines */}
              {diffData.diff?.length > 0 ? (
                <div style={{ borderTop: '1px solid var(--border)' }}>
                  {diffData.diff.map((line, idx) => renderDiffLine(line, idx))}
                </div>
              ) : (
                <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)', fontSize: 13 }}>
                  <CheckCircle size={32} style={{ marginBottom: 12, color: '#22c55e' }} />
                  <p style={{ margin: 0 }}>No textual differences detected between versions.</p>
                  {node.version_notes && (
                    <p style={{ marginTop: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
                      Version notes: {node.version_notes}
                    </p>
                  )}
                </div>
              )}
            </>
          ) : null}
        </div>
      </div>
    </div>
  )
}

const zoomBtnStyle = {
  width: 36, height: 36, borderRadius: 10, background: 'var(--card-bg)', border: '1px solid var(--border)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-secondary)',
  cursor: 'pointer', boxShadow: 'var(--shadow-sm)', transition: 'all 0.2s'
}

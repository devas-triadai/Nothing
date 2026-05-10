import { useState, useEffect, useRef, useCallback } from 'react'
import { apiFetch } from '../utils/api'
import { Network, Search, Filter, Maximize2, GitBranch, ArrowLeft, RefreshCw, ZoomIn, ZoomOut } from 'lucide-react'
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

export default function Genealogy() {
  const [nodes, setNodes] = useState([])
  const [edges, setEdges] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedNode, setSelectedNode] = useState(null)
  
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
      // Fetch all docs for the global graph
      const data = await apiFetch('/documents/lineage/all')
      if (data && data.nodes) {
        setNodes(data.nodes)
        setEdges(data.edges)
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  // ── D3 Force-Directed Graph ──
  useEffect(() => {
    if (loading || !nodes.length || !svgRef.current) return

    const width = containerRef.current.clientWidth
    const height = containerRef.current.clientHeight

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    // Add a defs section for arrowheads
    const defs = svg.append('defs')
    defs.append('marker')
      .attr('id', 'arrow')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 22) // shift arrow so it doesn't overlap node
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('fill', 'var(--text-muted)')
      .attr('d', 'M0,-5L10,0L0,5')

    const g = svg.append('g')

    // Zoom behavior
    const zoom = d3.zoom()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => g.attr('transform', event.transform))
    
    svg.call(zoom)
    zoomRef.current = zoom

    // Prepare data for D3
    const graphNodes = nodes.map(n => ({ ...n, radius: 16 }))
    
    // Edges need direct references to nodes array
    const graphEdges = edges.map(e => ({
      source: graphNodes.find(n => n.id === e.from) || e.from,
      target: graphNodes.find(n => n.id === e.to) || e.to,
      type: 'derived'
    })).filter(e => e.source && e.target && typeof e.source === 'object' && typeof e.target === 'object')

    // Simulation
    const simulation = d3.forceSimulation(graphNodes)
      .force('link', d3.forceLink(graphEdges).id(d => d.id).distance(100))
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collide', d3.forceCollide().radius(30))

    simulationRef.current = simulation

    // Draw Links
    const link = g.append('g')
      .selectAll('line')
      .data(graphEdges)
      .join('line')
      .attr('stroke', 'var(--border)')
      .attr('stroke-width', 2)
      .attr('marker-end', 'url(#arrow)')

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
      .attr('box-shadow', '0 4px 10px rgba(0,0,0,0.2)')

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
  }, [nodes, edges, loading])

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
    const width = containerRef.current.clientWidth
    const height = containerRef.current.clientHeight
    d3.select(svgRef.current).transition().duration(500)
      .call(zoomRef.current.transform, d3.zoomIdentity)
  }

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1600, margin: '0 auto', height: 'calc(100vh - 80px)', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-heading)', margin: 0, display: 'flex', alignItems: 'center', gap: 10 }}>
            <Network size={24} color="#8b5cf6" />
            Document Genealogy
          </h1>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '4px 0 0' }}>
            Interactive force-directed graph of document lineage and versions
          </p>
        </div>
        
        <div style={{ display: 'flex', gap: 10 }}>
          <button onClick={fetchGraphData} title="Refresh Graph"
            style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--card-bg)', color: 'var(--text-secondary)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div style={{ display: 'flex', gap: 20, flex: 1, minHeight: 0 }}>
        
        {/* Graph Container */}
        <div 
          ref={containerRef}
          style={{ 
            flex: 1, background: 'var(--card-bg)', borderRadius: 16, border: '1px solid var(--border)', 
            position: 'relative', overflow: 'hidden', boxShadow: 'inset 0 0 40px rgba(0,0,0,0.02)'
          }}
        >
          {loading && (
            <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(255,255,255,0.05)', zIndex: 10 }}>
              <span style={{ color: 'var(--text-secondary)' }}>Loading genealogy map...</span>
            </div>
          )}
          
          {/* Zoom Controls */}
          <div style={{ position: 'absolute', bottom: 20, right: 20, display: 'flex', flexDirection: 'column', gap: 8, zIndex: 10 }}>
            <button onClick={() => handleZoom(1.2)} style={zoomBtnStyle}><ZoomIn size={16} /></button>
            <button onClick={() => handleResetZoom()} style={zoomBtnStyle}><Maximize2 size={16} /></button>
            <button onClick={() => handleZoom(0.8)} style={zoomBtnStyle}><ZoomOut size={16} /></button>
          </div>

          {/* Legend */}
          <div style={{ position: 'absolute', top: 20, left: 20, background: 'var(--card-bg)', padding: 12, borderRadius: 12, border: '1px solid var(--border)', boxShadow: '0 4px 12px rgba(0,0,0,0.05)', zIndex: 10 }}>
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 8 }}>Categories</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {Object.entries(CAT_COLORS).slice(0, 5).map(([cat, color]) => (
                <div key={cat} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ width: 10, height: 10, borderRadius: '50%', background: color }} />
                  <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{cat}</span>
                </div>
              ))}
            </div>
          </div>

          <svg ref={svgRef} style={{ width: '100%', height: '100%', display: 'block' }} />
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
              <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 600 }}>v{selectedNode.version || 1}</span>
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

const zoomBtnStyle = {
  width: 36, height: 36, borderRadius: 10, background: 'var(--card-bg)', border: '1px solid var(--border)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-secondary)',
  cursor: 'pointer', boxShadow: '0 4px 12px rgba(0,0,0,0.05)', transition: 'all 0.2s'
}

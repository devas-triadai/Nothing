/**
 * AGRA Agent — Lightweight Markdown Renderer
 * Converts markdown text to HTML for AI responses.
 */

/**
 * Parse markdown to HTML.
 * Supports: bold, italic, inline code, code blocks,
 * headers, bullets, numbered lists, blockquotes, links, tables.
 */
export function renderMarkdown(text) {
  if (!text) return '';

  let html = text;

  // Escape HTML first (but we'll unescape our generated tags after)
  html = html
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Code blocks (``` ... ```)
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    return `<pre><code class="lang-${lang}">${code.trim()}</code></pre>`;
  });

  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Headers
  html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

  // Bold + Italic
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  // Bold
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Italic
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

  // Blockquotes
  html = html.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');

  // Horizontal rules
  html = html.replace(/^---$/gm, '<hr />');

  // Unordered lists with nested support
  html = html.replace(/^(\s*)[-*] (.+)$/gm, (_, indent, item) => {
    return `<li>${item}</li>`;
  });
  // Wrap consecutive <li> items in <ul>
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');

  // Ordered lists
  html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

  // Links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

  // Tables — basic support
  const tableRegex = /(?:^\|.+\|$\n?)+/gm;
  html = html.replace(tableRegex, (tableBlock) => {
    const rows = tableBlock.trim().split('\n');
    if (rows.length < 2) return tableBlock;

    let tableHtml = '<table>';
    rows.forEach((row, idx) => {
      // Skip separator row (|---|---|)
      if (/^\|[\s-:|]+\|$/.test(row)) return;
      const cells = row.split('|').filter(c => c.trim());
      const tag = idx === 0 ? 'th' : 'td';
      const rowTag = idx === 0 ? 'thead' : 'tbody';
      if (idx === 0) tableHtml += `<${rowTag}><tr>`;
      else if (idx === 2 || (idx === 1 && !/^\|[\s-:|]+\|$/.test(rows[1])))
        tableHtml += '<tbody>';
      if (idx !== 0 || !/^\|[\s-:|]+\|$/.test(row))
        tableHtml += '<tr>' + cells.map(c => `<${tag}>${c.trim()}</${tag}>`).join('') + '</tr>';
      if (idx === 0) tableHtml += `</tr></${rowTag}>`;
    });
    tableHtml += '</tbody></table>';
    return tableHtml;
  });

  // Paragraphs — wrap remaining text lines
  html = html.replace(/^(?!<[a-z/])((?!<).+)$/gm, '<p>$1</p>');

  // Clean up: merge consecutive blockquotes
  html = html.replace(/<\/blockquote>\n<blockquote>/g, '\n');

  // Remove empty paragraphs
  html = html.replace(/<p><\/p>/g, '');

  return html;
}

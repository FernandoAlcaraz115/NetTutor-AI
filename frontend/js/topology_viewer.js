/**
 * Visualizador interactivo de Topología de Red en SVG estilo Cisco Packet Tracer
 * Incluye símbolos clásicos de Cisco (Router, Switch, PC, Server),
 * triángulos de estado de enlace (verde/ámbar/rojo) y cables diferenciados.
 */
export class TopologyViewer {
  constructor(svgElement, onSelectDevice) {
    this.svg = svgElement;
    this.onSelectDevice = onSelectDevice;
    this.topology = null;
    this.findings = [];
    this.selectedDeviceId = null;
    this.highlightedLinkIds = new Set();
    this.highlightedLinkStatus = null; // 'success' | 'failure' | null

    // Estado de paneo y zoom
    this.zoomLevel = 1.0;
    this.pan = { x: 0, y: 0 };
    this.isPanning = false;
    this.panStart = { x: 0, y: 0 };

    // Estado de arrastre (drag & drop de nodos)
    this.draggedNode = null;
    this.dragOffset = { x: 0, y: 0 };
    this.wasDragging = false;

    this.initEvents();
  }

  initEvents() {
    this.svg.addEventListener('mousemove', (e) => this.handleMouseMove(e));
    this.svg.addEventListener('mouseup', () => this.handleMouseUp());
    this.svg.addEventListener('mouseleave', () => this.handleMouseUp());

    // Zoom con rueda del ratón
    this.svg.addEventListener('wheel', (e) => {
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.08 : 0.92;
      this.setZoom(this.zoomLevel * zoomFactor);
    }, { passive: false });

    // Paneo con botón central o Shift + click
    this.svg.addEventListener('mousedown', (e) => {
      if (e.button === 1 || (e.button === 0 && e.shiftKey)) {
        this.isPanning = true;
        this.panStart.x = e.clientX - this.pan.x;
        this.panStart.y = e.clientY - this.pan.y;
        this.svg.style.cursor = 'grabbing';
      }
    });
  }

  setZoom(newZoom) {
    this.zoomLevel = Math.max(0.45, Math.min(2.5, newZoom));
    this.applyTransform();
  }

  resetView() {
    this.zoomLevel = 1.0;
    this.pan = { x: 0, y: 0 };
    this.highlightedLinkIds.clear();
    this.highlightedLinkStatus = null;
    this.applyTransform();
  }

  highlightPingPath(linkIds = [], success = true) {
    this.highlightedLinkIds = new Set(linkIds || []);
    this.highlightedLinkStatus = linkIds && linkIds.length ? (success ? 'success' : 'failure') : null;
    if (this.topology) {
      this.render(this.topology, this.findings);
    }
  }

  applyTransform() {
    const rootG = this.svg.getElementById('viewport-group');
    if (rootG) {
      rootG.setAttribute('transform', `translate(${this.pan.x}, ${this.pan.y}) scale(${this.zoomLevel})`);
    }
  }

  render(topology, findings = []) {
    this.topology = topology;
    this.findings = findings;
    this.svg.innerHTML = '';

    if (!topology || !topology.devices) return;

    // Definiciones de gradientes y filtros estilo Packet Tracer
    this.renderDefs();

    // Grupo raíz que maneja zoom y desplazamiento
    const rootG = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    rootG.setAttribute('id', 'viewport-group');
    rootG.setAttribute('transform', `translate(${this.pan.x}, ${this.pan.y}) scale(${this.zoomLevel})`);
    this.svg.appendChild(rootG);

    // 1. Capa de enlaces
    const linksGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    linksGroup.setAttribute('id', 'links-layer');
    rootG.appendChild(linksGroup);

    // 2. Capa de nodos de dispositivos
    const nodesGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    nodesGroup.setAttribute('id', 'nodes-layer');
    rootG.appendChild(nodesGroup);

    this.renderLinks(linksGroup);
    this.renderNodes(nodesGroup);
  }

  renderDefs() {
    const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
    defs.innerHTML = `
      <linearGradient id="pt-cisco-blue-top" x1="0%" y1="0%" x2="0%" y2="100%">
        <stop offset="0%" stop-color="#4DA8E8" />
        <stop offset="100%" stop-color="#1E74B5" />
      </linearGradient>
      <linearGradient id="pt-cisco-blue-body" x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%" stop-color="#15578A" />
        <stop offset="50%" stop-color="#2580C4" />
        <stop offset="100%" stop-color="#124A75" />
      </linearGradient>
      <linearGradient id="pt-switch-top" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#53B2F0" />
        <stop offset="100%" stop-color="#1F75B8" />
      </linearGradient>
      <linearGradient id="pt-switch-front" x1="0%" y1="0%" x2="0%" y2="100%">
        <stop offset="0%" stop-color="#1C67A3" />
        <stop offset="100%" stop-color="#12456E" />
      </linearGradient>
      <linearGradient id="pt-pc-screen" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#7DD3FC" />
        <stop offset="100%" stop-color="#0284C7" />
      </linearGradient>
      <linearGradient id="pt-pc-chassis" x1="0%" y1="0%" x2="0%" y2="100%">
        <stop offset="0%" stop-color="#E2E8F0" />
        <stop offset="100%" stop-color="#94A3B8" />
      </linearGradient>
      <linearGradient id="pt-server-body" x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%" stop-color="#CBD5E1" />
        <stop offset="65%" stop-color="#94A3B8" />
        <stop offset="100%" stop-color="#64748B" />
      </linearGradient>
      <filter id="pt-node-shadow" x="-20%" y="-20%" width="140%" height="140%">
        <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#0F172A" flood-opacity="0.22" />
      </filter>
    `;
    this.svg.appendChild(defs);
  }

  _canonicalIf(name) {
    if (!name) return '';
    return name
      .trim()
      .toLowerCase()
      .replace(/\s+/g, '')
      .replace(/^fastethernet/, 'fa')
      .replace(/^gigabitethernet/, 'gi')
      .replace(/^tengigabitethernet/, 'te')
      .replace(/^ethernet/, 'eth')
      .replace(/^serial/, 'se');
  }

  _findInterface(dev, portName) {
    if (!dev || !dev.interfaces) return null;
    const target = this._canonicalIf(portName);
    return dev.interfaces.find(i => i.name === portName || this._canonicalIf(i.name) === target) || null;
  }

  _getPortLedColor(dev, portName, linkStatus, hasLinkError) {
    if (linkStatus === 'down') return '#EF4444';
    const iface = this._findInterface(dev, portName);
    if (iface && iface.status !== 'up') return '#EF4444';
    if (hasLinkError) return '#F59E0B';
    return '#22C55E';
  }

  renderLinks(container) {
    const deviceMap = new Map(this.topology.devices.map(d => [d.id, d]));

    this.topology.links.forEach(link => {
      const source = deviceMap.get(link.source_device);
      const target = deviceMap.get(link.target_device);
      if (!source || !target) return;

      const hasError = this.findings.some(f =>
        f.severity === 'error' && (
          (f.device_id === source.id && f.related_device_id === target.id) ||
          (f.device_id === target.id && f.related_device_id === source.id)
        )
      );

      const isPingHighlighted = this.highlightedLinkIds.has(link.id);
      const pingClass = isPingHighlighted
        ? (this.highlightedLinkStatus === 'success' ? 'ping-success' : 'ping-failure')
        : '';

      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.setAttribute('class', 'link-group');
      g.setAttribute('id', `link-group-${link.id}`);

      // Cable principal diferenciado por tipo (estilo Packet Tracer)
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', source.pos_x);
      line.setAttribute('y1', source.pos_y);
      line.setAttribute('x2', target.pos_x);
      line.setAttribute('y2', target.pos_y);
      const cableClass = `cable-${link.link_type || 'copper_straight'}`;
      line.setAttribute('class', `topology-link ${cableClass} ${hasError ? 'error' : ''} ${pingClass}`.trim());
      line.setAttribute('id', `line-${link.id}`);
      g.appendChild(line);

      const midX = (source.pos_x + target.pos_x) / 2;
      const midY = (source.pos_y + target.pos_y) / 2;

      // Triángulos de estado de enlace estilo Packet Tracer en ambos extremos
      const srcColor = this._getPortLedColor(source, link.source_interface, link.status, hasError);
      const tgtColor = this._getPortLedColor(target, link.target_interface, link.status, hasError);

      const srcTri = this.createLinkTriangle(source.pos_x, source.pos_y, target.pos_x, target.pos_y, 34, srcColor, 'src-link-tri');
      const tgtTri = this.createLinkTriangle(target.pos_x, target.pos_y, source.pos_x, source.pos_y, 34, tgtColor, 'tgt-link-tri');
      g.appendChild(srcTri);
      g.appendChild(tgtTri);

      // Etiquetas de puerto en los extremos
      const srcLabel = this.createPortBadge(
        source.pos_x + (midX - source.pos_x) * 0.44,
        source.pos_y + (midY - source.pos_y) * 0.44,
        this.shortenInterface(link.source_interface),
        'src-port-label'
      );
      g.appendChild(srcLabel);

      const tgtLabel = this.createPortBadge(
        target.pos_x + (midX - target.pos_x) * 0.44,
        target.pos_y + (midY - target.pos_y) * 0.44,
        this.shortenInterface(link.target_interface),
        'tgt-port-label'
      );
      g.appendChild(tgtLabel);

      // Badge de error en el punto medio si hay falla en el enlace
      if (hasError) {
        const errorBadge = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        errorBadge.setAttribute('class', 'link-error-badge');
        errorBadge.setAttribute('transform', `translate(${midX}, ${midY})`);

        const bg = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        bg.setAttribute('r', '8.5');
        bg.setAttribute('fill', '#DC2626');
        bg.setAttribute('stroke', '#FFFFFF');
        bg.setAttribute('stroke-width', '1.5');
        errorBadge.appendChild(bg);

        const icon = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        icon.setAttribute('d', 'M0 -3.5 L0 1 M0 3 L0 3.5');
        icon.setAttribute('stroke', '#FFFFFF');
        icon.setAttribute('stroke-width', '1.7');
        icon.setAttribute('stroke-linecap', 'round');
        errorBadge.appendChild(icon);

        g.appendChild(errorBadge);
      }

      container.appendChild(g);
    });
  }

  createLinkTriangle(x1, y1, x2, y2, distFromStart, fillColor, className) {
    const dx = x2 - x1;
    const dy = y2 - y1;
    const len = Math.hypot(dx, dy) || 1;
    const clampedDist = Math.min(distFromStart, len * 0.32);
    const px = x1 + (dx / len) * clampedDist;
    const py = y1 + (dy / len) * clampedDist;
    const angleDeg = (Math.atan2(dy, dx) * 180) / Math.PI;

    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('class', `link-status-triangle ${className}`);
    g.setAttribute('transform', `translate(${px.toFixed(1)}, ${py.toFixed(1)}) rotate(${angleDeg.toFixed(1)})`);

    const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    poly.setAttribute('points', '5,0 -4,-4.5 -4,4.5');
    poly.setAttribute('fill', fillColor);
    poly.setAttribute('stroke', '#FFFFFF');
    poly.setAttribute('stroke-width', '0.9');
    g.appendChild(poly);

    return g;
  }

  createPortBadge(x, y, text, extraClass = '') {
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('transform', `translate(${x}, ${y})`);
    if (extraClass) g.setAttribute('class', extraClass);

    const width = Math.max(26, text.length * 6.2 + 8);
    const height = 14;

    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', -width / 2);
    rect.setAttribute('y', -height / 2);
    rect.setAttribute('width', width);
    rect.setAttribute('height', height);
    rect.setAttribute('class', 'link-label-rect');
    g.appendChild(rect);

    const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    txt.setAttribute('text-anchor', 'middle');
    txt.setAttribute('y', 3.5);
    txt.setAttribute('class', 'link-label-text');
    txt.textContent = text;
    g.appendChild(txt);

    return g;
  }

  shortenInterface(name) {
    if (!name) return '';
    return name
      .replace('FastEthernet', 'Fa')
      .replace('GigabitEthernet', 'Gi')
      .replace('Serial', 'Se');
  }

  renderNodes(container) {
    this.topology.devices.forEach(dev => {
      const devErrors = this.findings.filter(f => f.device_id === dev.id && f.severity === 'error').length;
      const devWarnings = this.findings.filter(f => f.device_id === dev.id && f.severity === 'warning').length;

      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.setAttribute('class', `topology-node ${this.selectedDeviceId === dev.id ? 'highlighted' : ''}`);
      g.setAttribute('id', `node-${dev.id}`);
      g.setAttribute('transform', `translate(${dev.pos_x}, ${dev.pos_y})`);

      // Halo de selección estilo Packet Tracer
      const selRing = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      selRing.setAttribute('x', -36);
      selRing.setAttribute('y', -30);
      selRing.setAttribute('width', 72);
      selRing.setAttribute('height', 60);
      selRing.setAttribute('rx', 10);
      selRing.setAttribute('class', 'pt-selection-ring');
      g.appendChild(selRing);

      // Símbolo gráfico clásico de Cisco Packet Tracer
      const iconGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      iconGroup.setAttribute('class', 'pt-device-symbol');
      iconGroup.setAttribute('filter', 'url(#pt-node-shadow)');
      iconGroup.innerHTML = this.getPacketTracerSymbol(dev.type);
      g.appendChild(iconGroup);

      // Badge de error/advertencia en esquina del dispositivo
      if (devErrors > 0 || devWarnings > 0) {
        const badgeG = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        badgeG.setAttribute('transform', 'translate(22, -20)');
        const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        c.setAttribute('r', '8');
        c.setAttribute('fill', devErrors > 0 ? '#DC2626' : '#D97706');
        c.setAttribute('stroke', '#FFFFFF');
        c.setAttribute('stroke-width', '1.5');
        badgeG.appendChild(c);

        const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        t.setAttribute('text-anchor', 'middle');
        t.setAttribute('y', '3');
        t.setAttribute('fill', '#FFFFFF');
        t.setAttribute('font-size', '9px');
        t.setAttribute('font-weight', '700');
        t.textContent = String(devErrors > 0 ? devErrors : devWarnings);
        badgeG.appendChild(t);
        g.appendChild(badgeG);
      }

      // Etiqueta de nombre debajo del icono (como en Packet Tracer)
      const labelBgWidth = Math.max(54, dev.name.length * 6.8 + 12);
      const nameBg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      nameBg.setAttribute('x', -labelBgWidth / 2);
      nameBg.setAttribute('y', 23);
      nameBg.setAttribute('width', labelBgWidth);
      nameBg.setAttribute('height', 16);
      nameBg.setAttribute('rx', 4);
      nameBg.setAttribute('class', 'pt-label-bg');
      g.appendChild(nameBg);

      const nameText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      nameText.setAttribute('x', 0);
      nameText.setAttribute('y', 34.5);
      nameText.setAttribute('text-anchor', 'middle');
      nameText.setAttribute('class', 'node-title');
      nameText.textContent = dev.name;
      g.appendChild(nameText);

      // Subtítulo IP discreto debajo del nombre
      const mainIp = dev.interfaces.find(i => i.ip_address && i.ip_address !== 'unassigned')?.ip_address;
      if (mainIp) {
        const subText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        subText.setAttribute('x', 0);
        subText.setAttribute('y', 49);
        subText.setAttribute('text-anchor', 'middle');
        subText.setAttribute('class', 'node-subtitle');
        subText.textContent = mainIp;
        g.appendChild(subText);
      }

      // Eventos de arrastre y selección
      g.addEventListener('mousedown', (e) => {
        if (e.button === 0 && !e.shiftKey) {
          this.handleMouseDown(e, dev);
        }
      });
      g.addEventListener('click', (e) => {
        e.stopPropagation();
        if (!this.wasDragging) {
          this.selectDevice(dev.id);
        }
      });

      container.appendChild(g);
    });
  }

  /**
   * Símbolos SVG inspirados directamente en Cisco Packet Tracer
   */
  getPacketTracerSymbol(type) {
    switch (type) {
      case 'router':
        // Cilindro clásico Cisco Router azul con 4 flechas cruzadas en la tapa superior
        return `
          <path d="M -24 -6 L -24 10 A 24 11 0 0 0 24 10 L 24 -6 Z" fill="url(#pt-cisco-blue-body)" stroke="#0F3C61" stroke-width="1.3"/>
          <ellipse cx="0" cy="-6" rx="24" ry="11" fill="url(#pt-cisco-blue-top)" stroke="#0F3C61" stroke-width="1.3"/>
          <!-- Flechas cruzadas blancas estilo Cisco Router -->
          <path d="M -13 -10 L -4 -7 M -4 -7 L -8 -5 M -4 -7 L -5 -10.5" stroke="#FFFFFF" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
          <path d="M 13 -2 L 4 -5 M 4 -5 L 8 -7 M 4 -5 L 5 -1.5" stroke="#FFFFFF" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
          <path d="M -4 -5 L -13 -2 M -13 -2 L -9 -1 M -13 -2 L -11 -5.2" stroke="#FFFFFF" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
          <path d="M 4 -7 L 13 -10 M 13 -10 L 9 -11 M 13 -10 L 11 -6.8" stroke="#FFFFFF" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
        `;
      case 'switch':
        // Caja 3D clásica Cisco Switch 2960 azul con flechas opuestas arriba y LEDs frontales
        return `
          <!-- Cara superior isométrica -->
          <polygon points="-22,-13 22,-13 28,-3 -28,-3" fill="url(#pt-switch-top)" stroke="#0F3C61" stroke-width="1.2" stroke-linejoin="round"/>
          <!-- Cara frontal -->
          <rect x="-28" y="-3" width="56" height="15" rx="1.5" fill="url(#pt-switch-front)" stroke="#0F3C61" stroke-width="1.2"/>
          <!-- Flechas opuestas en la tapa -->
          <path d="M -13 -10 L 6 -10 M 3 -12 L 6 -10 L 3 -8" stroke="#FFFFFF" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
          <path d="M 13 -6 L -6 -6 M -3 -8 L -6 -6 L -3 -4" stroke="#FFFFFF" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
          <!-- Puertos y LEDs frontales -->
          <rect x="-22" y="2" width="32" height="5" rx="1" fill="#0B2D48" opacity="0.7"/>
          <circle cx="16" cy="4.5" r="1.5" fill="#4ADE80"/>
          <circle cx="21" cy="4.5" r="1.5" fill="#4ADE80"/>
        `;
      case 'server':
        // Torre de Servidor estilo Packet Tracer con bahías frontales y LEDs
        return `
          <rect x="-15" y="-22" width="30" height="39" rx="2.5" fill="url(#pt-server-body)" stroke="#334155" stroke-width="1.3"/>
          <rect x="-11" y="-17" width="22" height="5" rx="1" fill="#334155"/>
          <rect x="-11" y="-10" width="22" height="5" rx="1" fill="#334155"/>
          <rect x="-11" y="-3" width="22" height="4" rx="1" fill="#475569"/>
          <!-- Rejilla inferior -->
          <line x1="-10" y1="5" x2="10" y2="5" stroke="#475569" stroke-width="1.3"/>
          <line x1="-10" y1="8.5" x2="10" y2="8.5" stroke="#475569" stroke-width="1.3"/>
          <line x1="-10" y1="12" x2="10" y2="12" stroke="#475569" stroke-width="1.3"/>
          <!-- LEDs de estado -->
          <circle cx="8" cy="-14.5" r="1.3" fill="#22C55E"/>
          <circle cx="8" cy="-7.5" r="1.3" fill="#38BDF8"/>
        `;
      case 'pc':
      default:
        // Computadora de escritorio estilo Packet Tracer (Monitor + base + teclado)
        return `
          <!-- Marco del monitor -->
          <rect x="-21" y="-21" width="42" height="27" rx="3" fill="url(#pt-pc-chassis)" stroke="#334155" stroke-width="1.3"/>
          <!-- Pantalla azul -->
          <rect x="-17.5" y="-17.5" width="35" height="20" rx="1.5" fill="url(#pt-pc-screen)" stroke="#0369A1" stroke-width="0.9"/>
          <!-- Brillo sutil en pantalla -->
          <polygon points="-16,-16 -2,-16 -16,-5" fill="#FFFFFF" opacity="0.22"/>
          <!-- Pedestal -->
          <rect x="-5" y="6" width="10" height="5" fill="#64748B"/>
          <!-- Base / Teclado -->
          <polygon points="-16,11 16,11 20,16 -20,16" fill="#CBD5E1" stroke="#475569" stroke-width="1.1" stroke-linejoin="round"/>
        `;
    }
  }

  selectDevice(deviceId) {
    this.selectedDeviceId = deviceId;
    const dev = this.topology.devices.find(d => d.id === deviceId);
    if (this.onSelectDevice && dev) {
      this.onSelectDevice(dev);
    }
    this.render(this.topology, this.findings);
  }

  highlightDevices(deviceIds) {
    if (!deviceIds || !deviceIds.length) return;
    this.selectedDeviceId = deviceIds[0];
    this.render(this.topology, this.findings);
  }

  handleMouseDown(e, dev) {
    this.draggedNode = dev;
    this.wasDragging = false;
    const rect = this.svg.getBoundingClientRect();
    const mouseX = (e.clientX - rect.left - this.pan.x) / this.zoomLevel;
    const mouseY = (e.clientY - rect.top - this.pan.y) / this.zoomLevel;
    this.dragOffset.x = mouseX - dev.pos_x;
    this.dragOffset.y = mouseY - dev.pos_y;
  }

  handleMouseMove(e) {
    if (this.isPanning) {
      this.pan.x = e.clientX - this.panStart.x;
      this.pan.y = e.clientY - this.panStart.y;
      this.applyTransform();
      return;
    }

    if (!this.draggedNode) return;
    const rect = this.svg.getBoundingClientRect();
    const mouseX = (e.clientX - rect.left - this.pan.x) / this.zoomLevel;
    const mouseY = (e.clientY - rect.top - this.pan.y) / this.zoomLevel;

    const newX = Math.round(mouseX - this.dragOffset.x);
    const newY = Math.round(mouseY - this.dragOffset.y);
    if (Math.abs(newX - this.draggedNode.pos_x) > 2 || Math.abs(newY - this.draggedNode.pos_y) > 2) {
      this.wasDragging = true;
    }
    this.draggedNode.pos_x = newX;
    this.draggedNode.pos_y = newY;

    const nodeEl = this.svg.getElementById(`node-${this.draggedNode.id}`);
    if (nodeEl) {
      nodeEl.setAttribute('transform', `translate(${newX}, ${newY})`);
    }

    this.updateConnectedLinks(this.draggedNode);
  }

  updateConnectedLinks(dev) {
    if (!this.topology || !this.topology.links) return;
    const deviceMap = new Map(this.topology.devices.map(d => [d.id, d]));

    this.topology.links.forEach(link => {
      if (link.source_device !== dev.id && link.target_device !== dev.id) return;

      const source = deviceMap.get(link.source_device);
      const target = deviceMap.get(link.target_device);
      if (!source || !target) return;

      const line = this.svg.getElementById(`line-${link.id}`);
      if (line) {
        line.setAttribute('x1', source.pos_x);
        line.setAttribute('y1', source.pos_y);
        line.setAttribute('x2', target.pos_x);
        line.setAttribute('y2', target.pos_y);
      }

      const linkGroup = this.svg.getElementById(`link-group-${link.id}`);
      if (!linkGroup) return;

      const midX = (source.pos_x + target.pos_x) / 2;
      const midY = (source.pos_y + target.pos_y) / 2;

      const dx = target.pos_x - source.pos_x;
      const dy = target.pos_y - source.pos_y;
      const len = Math.hypot(dx, dy) || 1;
      const dist = Math.min(34, len * 0.32);

      const srcTri = linkGroup.querySelector('.src-link-tri');
      if (srcTri) {
        const px = source.pos_x + (dx / len) * dist;
        const py = source.pos_y + (dy / len) * dist;
        const ang = (Math.atan2(dy, dx) * 180) / Math.PI;
        srcTri.setAttribute('transform', `translate(${px.toFixed(1)}, ${py.toFixed(1)}) rotate(${ang.toFixed(1)})`);
      }

      const tgtTri = linkGroup.querySelector('.tgt-link-tri');
      if (tgtTri) {
        const px = target.pos_x - (dx / len) * dist;
        const py = target.pos_y - (dy / len) * dist;
        const ang = (Math.atan2(-dy, -dx) * 180) / Math.PI;
        tgtTri.setAttribute('transform', `translate(${px.toFixed(1)}, ${py.toFixed(1)}) rotate(${ang.toFixed(1)})`);
      }

      const srcBadge = linkGroup.querySelector('.src-port-label');
      if (srcBadge) {
        const sx = source.pos_x + (midX - source.pos_x) * 0.44;
        const sy = source.pos_y + (midY - source.pos_y) * 0.44;
        srcBadge.setAttribute('transform', `translate(${sx}, ${sy})`);
      }

      const tgtBadge = linkGroup.querySelector('.tgt-port-label');
      if (tgtBadge) {
        const tx = target.pos_x + (midX - target.pos_x) * 0.44;
        const ty = target.pos_y + (midY - target.pos_y) * 0.44;
        tgtBadge.setAttribute('transform', `translate(${tx}, ${ty})`);
      }

      const errorBadge = linkGroup.querySelector('.link-error-badge');
      if (errorBadge) {
        errorBadge.setAttribute('transform', `translate(${midX}, ${midY})`);
      }
    });
  }

  handleMouseUp() {
    this.draggedNode = null;
    if (this.isPanning) {
      this.isPanning = false;
      this.svg.style.cursor = 'default';
    }
  }
}

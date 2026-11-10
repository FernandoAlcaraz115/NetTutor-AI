/**
 * Visualizador interactivo de Topología de Red en SVG para NetTutorIA
 * Diseño: Enterprise Network Engineering UI (Minimalista, Sobrio, Técnico)
 */
export class TopologyViewer {
  constructor(svgElement, onSelectDevice) {
    this.svg = svgElement;
    this.onSelectDevice = onSelectDevice;
    this.topology = null;
    this.findings = [];
    this.selectedDeviceId = null;

    // Estado de paneo y zoom
    this.zoomLevel = 1.0;
    this.pan = { x: 0, y: 0 };
    this.isPanning = false;
    this.panStart = { x: 0, y: 0 };

    // Estado de arrastre (drag & drop de nodos)
    this.draggedNode = null;
    this.dragOffset = { x: 0, y: 0 };

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
    this.zoomLevel = Math.max(0.5, Math.min(2.5, newZoom));
    this.applyTransform();
  }

  resetView() {
    this.zoomLevel = 1.0;
    this.pan = { x: 0, y: 0 };
    this.applyTransform();
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
    this.svg.innerHTML = ''; // Limpiar lienzo

    if (!topology || !topology.devices) return;

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

    // Renderizar capas
    this.renderLinks(linksGroup);
    this.renderNodes(nodesGroup);
  }

  renderLinks(container) {
    const deviceMap = new Map(this.topology.devices.map(d => [d.id, d]));

    this.topology.links.forEach(link => {
      const source = deviceMap.get(link.source_device);
      const target = deviceMap.get(link.target_device);
      if (!source || !target) return;

      const hasError = this.findings.some(f => 
        (f.device_id === source.id && f.related_device_id === target.id) ||
        (f.device_id === target.id && f.related_device_id === source.id)
      );

      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.setAttribute('class', 'link-group');

      // Línea de conexión
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', source.pos_x);
      line.setAttribute('y1', source.pos_y);
      line.setAttribute('x2', target.pos_x);
      line.setAttribute('y2', target.pos_y);
      line.setAttribute('class', `topology-link ${hasError ? 'error' : ''}`);
      line.setAttribute('id', `line-${link.id}`);
      g.appendChild(line);

      // Etiquetas discretas de puerto en los extremos
      const midX = (source.pos_x + target.pos_x) / 2;
      const midY = (source.pos_y + target.pos_y) / 2;

      const srcLabel = this.createPortBadge(
        source.pos_x + (midX - source.pos_x) * 0.38,
        source.pos_y + (midY - source.pos_y) * 0.38,
        this.shortenInterface(link.source_interface)
      );
      g.appendChild(srcLabel);

      const tgtLabel = this.createPortBadge(
        target.pos_x + (midX - target.pos_x) * 0.38,
        target.pos_y + (midY - target.pos_y) * 0.38,
        this.shortenInterface(link.target_interface)
      );
      g.appendChild(tgtLabel);

      // Si tiene error, colocar indicador visual discreto en el punto medio
      if (hasError) {
        const errorBadge = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        errorBadge.setAttribute('transform', `translate(${midX}, ${midY})`);

        const bg = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        bg.setAttribute('r', '8');
        bg.setAttribute('fill', '#DC2626');
        bg.setAttribute('stroke', '#FFFFFF');
        bg.setAttribute('stroke-width', '1.5');
        errorBadge.appendChild(bg);

        const icon = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        icon.setAttribute('d', 'M0 -3.5 L0 1 M0 3 L0 3.5');
        icon.setAttribute('stroke', '#FFFFFF');
        icon.setAttribute('stroke-width', '1.6');
        icon.setAttribute('stroke-linecap', 'round');
        errorBadge.appendChild(icon);

        g.appendChild(errorBadge);
      }

      container.appendChild(g);
    });
  }

  createPortBadge(x, y, text) {
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('transform', `translate(${x}, ${y})`);

    const width = Math.max(26, text.length * 6.5 + 8);
    const height = 15;

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
      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.setAttribute('class', `topology-node ${this.selectedDeviceId === dev.id ? 'highlighted' : ''}`);
      g.setAttribute('id', `node-${dev.id}`);
      g.setAttribute('transform', `translate(${dev.pos_x}, ${dev.pos_y})`);

      // Tarjeta base del dispositivo
      const cardWidth = 84;
      const cardHeight = 48;
      const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      rect.setAttribute('x', -cardWidth / 2);
      rect.setAttribute('y', -cardHeight / 2);
      rect.setAttribute('width', cardWidth);
      rect.setAttribute('height', cardHeight);
      rect.setAttribute('class', 'node-card-bg');
      g.appendChild(rect);

      // Banda de acento según tipo de dispositivo en la parte superior de la tarjeta
      const accent = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      const x0 = -cardWidth / 2;
      const y0 = -cardHeight / 2;
      accent.setAttribute('d', `M ${x0 + 6} ${y0} L ${x0 + cardWidth - 6} ${y0} A 6 6 0 0 1 ${x0 + cardWidth} ${y0 + 6} L ${x0 + cardWidth} ${y0 + 3} L ${x0} ${y0 + 3} L ${x0} ${y0 + 6} A 6 6 0 0 1 ${x0 + 6} ${y0} Z`);
      accent.setAttribute('fill', this.getNodeAccentColor(dev.type));
      g.appendChild(accent);

      // Icono vectorial profesional según DeviceType
      const iconGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      iconGroup.setAttribute('transform', 'translate(-28, -6)');
      iconGroup.innerHTML = this.getDeviceVectorIcon(dev.type);
      g.appendChild(iconGroup);

      // Nombre del dispositivo
      const nameText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      nameText.setAttribute('x', -10);
      nameText.setAttribute('y', -4);
      nameText.setAttribute('class', 'node-title');
      nameText.textContent = dev.name;
      g.appendChild(nameText);

      // Subtítulo técnico (IP principal o tipo abreviado)
      const mainIp = dev.interfaces.find(i => i.ip_address)?.ip_address;
      const subText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      subText.setAttribute('x', -10);
      subText.setAttribute('y', 10);
      subText.setAttribute('class', 'node-subtitle');
      subText.textContent = mainIp || dev.type.toUpperCase();
      g.appendChild(subText);

      // Eventos de arrastre y selección
      g.addEventListener('mousedown', (e) => {
        if (e.button === 0 && !e.shiftKey) {
          this.handleMouseDown(e, dev);
        }
      });
      g.addEventListener('click', (e) => {
        e.stopPropagation();
        this.selectDevice(dev.id);
      });

      container.appendChild(g);
    });
  }

  getNodeAccentColor(type) {
    switch (type) {
      case 'router': return '#0E7490';
      case 'switch': return '#1D4ED8';
      case 'pc': return '#0F766E';
      case 'server': return '#4338CA';
      default: return '#475569';
    }
  }

  getDeviceVectorIcon(type) {
    const color = this.getNodeAccentColor(type);
    switch (type) {
      case 'router':
        return `<circle cx="6" cy="6" r="7" fill="none" stroke="${color}" stroke-width="1.4"/>
                <path d="M2.5 6 L9.5 6 M6 2.5 L6 9.5" stroke="${color}" stroke-width="1.3" stroke-linecap="round"/>
                <path d="M4 4 L8 8 M4 8 L8 4" stroke="${color}" stroke-width="1" stroke-linecap="round"/>`;
      case 'switch':
        return `<rect x="0" y="2" width="12" height="8" rx="1.5" fill="none" stroke="${color}" stroke-width="1.4"/>
                <path d="M2.5 5 L6 5 L4.5 3.5 M6 5 L4.5 6.5" stroke="${color}" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M9.5 7 L6 7 L7.5 5.5 M6 7 L7.5 8.5" stroke="${color}" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>`;
      case 'server':
        return `<rect x="0" y="1" width="12" height="4.5" rx="1" fill="none" stroke="${color}" stroke-width="1.3"/>
                <rect x="0" y="6.5" width="12" height="4.5" rx="1" fill="none" stroke="${color}" stroke-width="1.3"/>
                <circle cx="2.5" cy="3.25" r="0.8" fill="${color}"/>
                <circle cx="2.5" cy="8.75" r="0.8" fill="${color}"/>`;
      case 'pc':
      default:
        return `<rect x="0" y="0.5" width="12" height="8.5" rx="1" fill="none" stroke="${color}" stroke-width="1.3"/>
                <path d="M3.5 11.5 L8.5 11.5 M6 9 L6 11.5" stroke="${color}" stroke-width="1.3" stroke-linecap="round"/>`;
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

    this.draggedNode.pos_x = Math.round(mouseX - this.dragOffset.x);
    this.draggedNode.pos_y = Math.round(mouseY - this.dragOffset.y);
    this.render(this.topology, this.findings);
  }

  handleMouseUp() {
    this.draggedNode = null;
    if (this.isPanning) {
      this.isPanning = false;
      this.svg.style.cursor = 'default';
    }
  }
}

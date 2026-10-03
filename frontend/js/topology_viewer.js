/**
 * Visualizador interactivo de Topología de Red en SVG para NetTutorIA
 */
export class TopologyViewer {
  constructor(svgElement, onSelectDevice) {
    this.svg = svgElement;
    this.onSelectDevice = onSelectDevice;
    this.topology = null;
    this.findings = [];
    this.selectedDeviceId = null;

    // Estado de arrastre (drag & drop)
    this.draggedNode = null;
    this.dragOffset = { x: 0, y: 0 };

    this.initEvents();
  }

  initEvents() {
    this.svg.addEventListener('mousemove', (e) => this.handleMouseMove(e));
    this.svg.addEventListener('mouseup', () => this.handleMouseUp());
    this.svg.addEventListener('mouseleave', () => this.handleMouseUp());
  }

  render(topology, findings = []) {
    this.topology = topology;
    this.findings = findings;
    this.svg.innerHTML = ''; // Limpiar lienzo

    if (!topology || !topology.devices) return;

    // Crear grupo para enlaces
    const linksGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    linksGroup.setAttribute('id', 'links-layer');
    this.svg.appendChild(linksGroup);

    // Crear grupo para nodos
    const nodesGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    nodesGroup.setAttribute('id', 'nodes-layer');
    this.svg.appendChild(nodesGroup);

    // Renderizar enlaces
    this.renderLinks(linksGroup);

    // Renderizar nodos de dispositivos
    this.renderNodes(nodesGroup);
  }

  renderLinks(container) {
    const deviceMap = new Map(this.topology.devices.map(d => [d.id, d]));

    this.topology.links.forEach(link => {
      const source = deviceMap.get(link.source_device);
      const target = deviceMap.get(link.target_device);
      if (!source || !target) return;

      // Buscar si este enlace tiene hallazgos / errores
      const hasError = this.findings.some(f => 
        (f.device_id === source.id && f.related_device_id === target.id) ||
        (f.device_id === target.id && f.related_device_id === source.id)
      );

      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.setAttribute('class', 'link-group');

      // Línea principal
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', source.pos_x);
      line.setAttribute('y1', source.pos_y);
      line.setAttribute('x2', target.pos_x);
      line.setAttribute('y2', target.pos_y);
      line.setAttribute('class', `topology-link ${hasError ? 'error' : ''}`);
      line.setAttribute('id', `line-${link.id}`);
      g.appendChild(line);

      // Etiquetas de interfaz
      const midX = (source.pos_x + target.pos_x) / 2;
      const midY = (source.pos_y + target.pos_y) / 2;

      // Etiqueta del origen (cerca del source)
      const srcLabel = this.createPortLabel(
        source.pos_x + (midX - source.pos_x) * 0.35,
        source.pos_y + (midY - source.pos_y) * 0.35,
        this.shortenInterface(link.source_interface)
      );
      g.appendChild(srcLabel);

      // Etiqueta del destino (cerca del target)
      const tgtLabel = this.createPortLabel(
        target.pos_x + (midX - target.pos_x) * 0.35,
        target.pos_y + (midY - target.pos_y) * 0.35,
        this.shortenInterface(link.target_interface)
      );
      g.appendChild(tgtLabel);

      // Si tiene error, colocar insignia de alerta pulsante en el medio
      if (hasError) {
        const alertIcon = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        alertIcon.setAttribute('cx', midX);
        alertIcon.setAttribute('cy', midY);
        alertIcon.setAttribute('r', 10);
        alertIcon.setAttribute('fill', '#ef4444');
        alertIcon.setAttribute('stroke', '#ffffff');
        alertIcon.setAttribute('stroke-width', '1.5');
        g.appendChild(alertIcon);

        const alertText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        alertText.setAttribute('x', midX);
        alertText.setAttribute('y', midY + 4);
        alertText.setAttribute('text-anchor', 'middle');
        alertText.setAttribute('fill', '#ffffff');
        alertText.setAttribute('font-size', '10px');
        alertText.setAttribute('font-weight', 'bold');
        alertText.textContent = '!';
        g.appendChild(alertText);
      }

      container.appendChild(g);
    });
  }

  createPortLabel(x, y, text) {
    const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    txt.setAttribute('x', x);
    txt.setAttribute('y', y);
    txt.setAttribute('fill', '#9ca3af');
    txt.setAttribute('font-size', '10px');
    txt.setAttribute('font-family', 'var(--font-mono)');
    txt.setAttribute('text-anchor', 'middle');
    txt.textContent = text;
    return txt;
  }

  shortenInterface(name) {
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

      // Círculo de fondo con efecto de brillo
      const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      circle.setAttribute('r', 26);
      circle.setAttribute('class', 'node-bg');
      circle.setAttribute('fill', this.getNodeColor(dev.type));
      circle.setAttribute('stroke', 'rgba(255, 255, 255, 0.2)');
      circle.setAttribute('stroke-width', '2');
      g.appendChild(circle);

      // Icono SVG / Texto según tipo
      const icon = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      icon.setAttribute('text-anchor', 'middle');
      icon.setAttribute('dy', 5);
      icon.setAttribute('font-size', '16px');
      icon.textContent = this.getNodeIcon(dev.type);
      g.appendChild(icon);

      // Etiqueta del nombre del dispositivo
      const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      label.setAttribute('text-anchor', 'middle');
      label.setAttribute('y', 42);
      label.setAttribute('fill', '#f9fafb');
      label.setAttribute('font-size', '12px');
      label.setAttribute('font-weight', '600');
      label.textContent = dev.name;
      g.appendChild(label);

      // Sub-etiqueta (tipo o IP principal)
      const sublabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      sublabel.setAttribute('text-anchor', 'middle');
      sublabel.setAttribute('y', 55);
      sublabel.setAttribute('fill', '#9ca3af');
      sublabel.setAttribute('font-size', '10px');
      sublabel.setAttribute('font-family', 'var(--font-mono)');
      
      const mainIp = dev.interfaces.find(i => i.ip_address)?.ip_address;
      sublabel.textContent = mainIp || dev.type.toUpperCase();
      g.appendChild(sublabel);

      // Eventos de arrastre y selección
      g.addEventListener('mousedown', (e) => this.handleMouseDown(e, dev));
      g.addEventListener('click', (e) => {
        e.stopPropagation();
        this.selectDevice(dev.id);
      });

      container.appendChild(g);
    });
  }

  getNodeColor(type) {
    switch (type) {
      case 'router': return '#0369a1';
      case 'switch': return '#4338ca';
      case 'pc': return '#0f766e';
      case 'server': return '#7c3aed';
      default: return '#374151';
    }
  }

  getNodeIcon(type) {
    switch (type) {
      case 'router': return '🌐';
      case 'switch': return '🔀';
      case 'pc': return '💻';
      case 'server': return '🖥️';
      default: return '📦';
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
    this.dragOffset.x = (e.clientX - rect.left) - dev.pos_x;
    this.dragOffset.y = (e.clientY - rect.top) - dev.pos_y;
  }

  handleMouseMove(e) {
    if (!this.draggedNode) return;
    const rect = this.svg.getBoundingClientRect();
    this.draggedNode.pos_x = Math.max(40, Math.min(rect.width - 40, (e.clientX - rect.left) - this.dragOffset.x));
    this.draggedNode.pos_y = Math.max(40, Math.min(rect.height - 60, (e.clientY - rect.top) - this.dragOffset.y));
    this.render(this.topology, this.findings);
  }

  handleMouseUp() {
    this.draggedNode = null;
  }
}

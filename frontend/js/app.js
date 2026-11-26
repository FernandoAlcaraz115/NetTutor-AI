import { ApiClient } from './api.js';
import { TopologyViewer } from './topology_viewer.js';
import { TutorChat } from './tutor_chat.js';
import { DiagnosticsPanel } from './diagnostics_panel.js';

class NetTutorApp {
  constructor() {
    this.currentTopology = null;
    this.currentReport = null;

    // Estado de inspección
    this.inspectedDeviceId = null;

    // Estado CLI
    this.currentCliMode = 'priv';
    this.currentCliInterface = null;
    this.cliHistory = [];
    this.cliHistoryIndex = -1;

    // Elementos DOM
    this.svg = document.getElementById('topology-svg');
    this.inspectPanel = document.getElementById('device-inspect-panel');
    this.inspectTitle = document.getElementById('inspect-device-name');
    this.inspectTbody = document.getElementById('inspect-table-body');
    this.scoreVal = document.getElementById('score-value');
    this.issuesSummary = document.getElementById('issues-summary');
    this.labTitle = document.getElementById('lab-title');
    this.labDesc = document.getElementById('lab-desc');
    this.ptStatusPill = document.getElementById('pt-status-pill');
    this.ptStatusDot = document.getElementById('pt-status-dot');
    this.ptStatusText = document.getElementById('pt-status-text');

    // Inicializar componentes
    this.topologyViewer = new TopologyViewer(this.svg, (dev) => this.showDeviceDetails(dev));
    
    this.diagnosticsPanel = new DiagnosticsPanel(
      document.getElementById('diagnostics-container'),
      (finding) => this.askTutorAboutFinding(finding)
    );

    this.tutorChat = new TutorChat(
      document.getElementById('chat-messages'),
      document.getElementById('chat-input'),
      document.getElementById('btn-send-chat'),
      (devIds) => this.topologyViewer.highlightDevices(devIds)
    );

    this.initEvents();
  }

  initEvents() {
    // Botón de re-analizar práctica
    document.getElementById('btn-run-diagnostics').addEventListener('click', () => {
      this.refreshDiagnostics();
    });

    // Pestañas laterales
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        
        e.currentTarget.classList.add('active');
        const tabTarget = e.currentTarget.dataset.tab;
        document.getElementById(`tab-${tabTarget}`).classList.add('active');
      });
    });

    // Cerrar panel de inspección de dispositivo
    document.getElementById('btn-close-inspect').addEventListener('click', () => {
      this.inspectPanel.classList.remove('active');
      this.inspectedDeviceId = null;
    });

    // Abrir CLI directo desde el panel de inspección (estilo Packet Tracer)
    const inspectCliBtn = document.getElementById('btn-inspect-open-cli');
    if (inspectCliBtn) {
      inspectCliBtn.addEventListener('click', () => {
        if (!this.inspectedDeviceId) return;
        const toolsTab = document.querySelector('[data-tab="tools"]');
        if (toolsTab) toolsTab.click();
        const cliSelect = document.getElementById('select-cli-device');
        if (cliSelect) {
          cliSelect.value = this.inspectedDeviceId;
          this.currentCliMode = 'priv';
          this.currentCliInterface = null;
          this.updateCliPrompt();
        }
        const cliInput = document.getElementById('cli-input-command');
        if (cliInput) cliInput.focus();
      });
    }

    // Modal Guía Rápida de Uso
    const helpModal = document.getElementById('modal-help');
    const openHelpBtn = document.getElementById('btn-open-help');
    const closeHelpBtn = document.getElementById('btn-close-help');
    const okHelpBtn = document.getElementById('btn-ok-help');
    const closeHelp = () => helpModal && helpModal.classList.remove('active');
    if (openHelpBtn && helpModal) {
      openHelpBtn.addEventListener('click', () => helpModal.classList.add('active'));
    }
    if (closeHelpBtn) closeHelpBtn.addEventListener('click', closeHelp);
    if (okHelpBtn) okHelpBtn.addEventListener('click', closeHelp);

    // Modal Importar Config
    const modal = document.getElementById('modal-import');
    const openImportBtn = document.getElementById('btn-open-import');
    const closeImportBtn = document.getElementById('btn-close-import');
    const cancelImportBtn = document.getElementById('btn-cancel-import');

    if (openImportBtn) {
      openImportBtn.addEventListener('click', () => {
        modal.classList.add('active');
      });
    }

    const closeModal = () => modal.classList.remove('active');
    if (closeImportBtn) closeImportBtn.addEventListener('click', closeModal);
    if (cancelImportBtn) cancelImportBtn.addEventListener('click', closeModal);

    document.getElementById('btn-submit-import').addEventListener('click', () => {
      this.handleImportConfig();
    });

    // Selector de Prácticas
    document.getElementById('select-lab').addEventListener('change', async (e) => {
      const presetId = e.target.value;
      if (!presetId) return;
      try {
        const loadedTopo = await ApiClient.loadPreset(presetId);
        this.currentTopology = loadedTopo;
        this.labTitle.textContent = loadedTopo.name;
        this.labDesc.textContent = loadedTopo.description || 'Topología activa de red';
        this.resetLabUIState();
        this.topologyViewer.resetView();
        await this.refreshDiagnostics();
        this.populateToolSelectors();
        this.announceLoadedLab();
      } catch (err) {
        alert('Error al cargar la práctica: ' + err.message);
      }
    });

    // Subir archivo .PKT directo desde la computadora
    const fileInput = document.getElementById('input-upload-pkt');
    document.getElementById('btn-upload-pkt').addEventListener('click', () => {
      fileInput.click();
    });
    fileInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (file) {
        this.handleUploadPkt(file);
      }
      fileInput.value = '';
    });

    // Herramientas de Zoom y Reset de la Topología
    const zoomInBtn = document.getElementById('btn-zoom-in');
    const zoomOutBtn = document.getElementById('btn-zoom-out');
    const zoomResetBtn = document.getElementById('btn-zoom-reset');

    if (zoomInBtn) {
      zoomInBtn.addEventListener('click', () => {
        this.topologyViewer.setZoom(this.topologyViewer.zoomLevel * 1.15);
      });
    }
    if (zoomOutBtn) {
      zoomOutBtn.addEventListener('click', () => {
        this.topologyViewer.setZoom(this.topologyViewer.zoomLevel * 0.85);
      });
    }
    if (zoomResetBtn) {
      zoomResetBtn.addEventListener('click', () => {
        this.topologyViewer.resetView();
      });
    }

    // Selector de Modo Oscuro / Claro
    const themeBtn = document.getElementById('btn-theme-toggle');
    if (themeBtn) {
      themeBtn.addEventListener('click', () => {
        const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', newTheme);
        localStorage.setItem('nettutoria_theme', newTheme);
      });
    }

    // Herramienta 1: Simulador de Ping
    const runPingBtn = document.getElementById('btn-run-ping');
    if (runPingBtn) {
      runPingBtn.addEventListener('click', () => this.handleRunPing());
    }

    // Herramienta 2: CLI Interactiva en Vivo
    const cliInput = document.getElementById('cli-input-command');
    if (cliInput) {
      cliInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          this.handleExecuteCliCommand();
        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          if (this.cliHistory.length > 0) {
            if (this.cliHistoryIndex === -1) {
              this.cliHistoryIndex = this.cliHistory.length - 1;
            } else if (this.cliHistoryIndex > 0) {
              this.cliHistoryIndex--;
            }
            cliInput.value = this.cliHistory[this.cliHistoryIndex] || '';
          }
        } else if (e.key === 'ArrowDown') {
          e.preventDefault();
          if (this.cliHistory.length > 0 && this.cliHistoryIndex !== -1) {
            if (this.cliHistoryIndex < this.cliHistory.length - 1) {
              this.cliHistoryIndex++;
              cliInput.value = this.cliHistory[this.cliHistoryIndex] || '';
            } else {
              this.cliHistoryIndex = -1;
              cliInput.value = '';
            }
          }
        }
      });
    }

    const cliDevSelect = document.getElementById('select-cli-device');
    if (cliDevSelect) {
      cliDevSelect.addEventListener('change', () => {
        this.currentCliMode = 'priv';
        this.currentCliInterface = null;
        this.updateCliPrompt();
      });
    }

    // Herramienta 3: Exportar Reporte para Profesor
    const exportBtn = document.getElementById('btn-export-report');
    const modalReport = document.getElementById('modal-report');
    const closeReportBtn = document.getElementById('btn-close-report');
    const printReportBtn = document.getElementById('btn-print-report');

    if (exportBtn) {
      exportBtn.addEventListener('click', () => {
        this.generateEvaluationReport();
        modalReport.classList.add('active');
      });
    }
    if (closeReportBtn) {
      closeReportBtn.addEventListener('click', () => {
        modalReport.classList.remove('active');
      });
    }
    if (printReportBtn) {
      printReportBtn.addEventListener('click', () => {
        window.print();
      });
    }
  }

  initTheme() {
    const savedTheme = localStorage.getItem('nettutoria_theme');
    if (savedTheme) {
      document.documentElement.setAttribute('data-theme', savedTheme);
    } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      document.documentElement.setAttribute('data-theme', 'dark');
    }
  }

  async start() {
    this.initTheme();
    await this.loadPresetsList();
    await this.loadApp();
    this.checkPacketTracer();
    this.tutorWelcome();
  }

  async loadPresetsList() {
    try {
      const presets = await ApiClient.getPresets();
      const selectEl = document.getElementById('select-lab');
      selectEl.innerHTML = '';
      presets.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = p.name;
        selectEl.appendChild(opt);
      });
    } catch (e) {
      console.error('Error cargando lista de prácticas:', e);
    }
  }

  tutorWelcome() {
    this.tutorChat.addTutorMessage(
      "Hola. Soy **NetTutor**, tu asistente técnico para prácticas de redes Cisco.\n\n" +
      "He analizado la topología activa y contrastado su estado contra las reglas de consistencia de Capa 1, 2 y 3.\n\n" +
      "Selecciona un hallazgo en la pestaña de **Diagnóstico** o hazme una consulta para guiarte en la resolución del problema."
    );
  }

  announceLoadedLab() {
    if (!this.currentTopology || !this.currentReport) return;
    const issues = this.currentReport.total_issues;
    const msg = issues > 0
      ? `Práctica cargada: **${this.escapeHtml(this.currentTopology.name)}** (${this.currentTopology.devices.length} equipos, ${this.currentTopology.links.length} enlaces).\n\nSe identificaron **${issues} inconsistencia(s)** (Consistencia: **${this.currentReport.score_percentage}%**). Revisa la pestaña de Diagnóstico para ver los detalles técnicos.`
      : `Práctica cargada: **${this.escapeHtml(this.currentTopology.name)}** (${this.currentTopology.devices.length} equipos, ${this.currentTopology.links.length} enlaces).\n\nTodas las verificaciones técnicas concluyeron con **100% de consistencia**.`;
    this.tutorChat.addTutorMessage(msg);
  }

  escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  resetLabUIState() {
    this.inspectedDeviceId = null;
    this.inspectPanel.classList.remove('active');
    this.currentCliMode = 'priv';
    this.currentCliInterface = null;
    this.tutorChat.resetContext();
    const resBox = document.getElementById('ping-results-box');
    if (resBox) {
      resBox.style.display = 'none';
      resBox.innerHTML = '';
    }
  }

  async loadApp() {
    try {
      this.currentTopology = await ApiClient.getTopology();
      this.labTitle.textContent = this.currentTopology.name;
      this.labDesc.textContent = this.currentTopology.description || 'Topología activa de red';

      await this.refreshDiagnostics();
      this.populateToolSelectors();
    } catch (e) {
      console.error('Error cargando topología:', e);
    }
  }

  populateToolSelectors() {
    if (!this.currentTopology || !this.currentTopology.devices) return;
    const srcSelect = document.getElementById('select-ping-src');
    const tgtSelect = document.getElementById('select-ping-tgt');
    const cliSelect = document.getElementById('select-cli-device');

    if (srcSelect && tgtSelect) {
      srcSelect.innerHTML = '';
      tgtSelect.innerHTML = '';
      this.currentTopology.devices.forEach((d, idx) => {
        const opt1 = document.createElement('option');
        opt1.value = d.id;
        opt1.textContent = `${d.name} (${d.type.toUpperCase()})`;
        const opt2 = document.createElement('option');
        opt2.value = d.id;
        opt2.textContent = `${d.name} (${d.type.toUpperCase()})`;
        srcSelect.appendChild(opt1);
        tgtSelect.appendChild(opt2);
      });
      if (tgtSelect.options.length > 1) {
        tgtSelect.selectedIndex = tgtSelect.options.length - 1;
      }
    }

    if (cliSelect) {
      cliSelect.innerHTML = '';
      const ciscoDevices = this.currentTopology.devices.filter(d => d.type === 'switch' || d.type === 'router');
      (ciscoDevices.length ? ciscoDevices : this.currentTopology.devices).forEach(d => {
        const opt = document.createElement('option');
        opt.value = d.id;
        opt.textContent = `${d.name} (${d.type.toUpperCase()})`;
        cliSelect.appendChild(opt);
      });
      this.updateCliPrompt();
    }
  }

  updateCliPrompt() {
    const cliSelect = document.getElementById('select-cli-device');
    const promptEl = document.getElementById('cli-prompt');
    if (!cliSelect || !promptEl) return;
    const devId = cliSelect.value || 'Device';
    const dev = this.currentTopology ? this.currentTopology.devices.find(d => d.id === devId) : null;
    const name = dev ? dev.name : devId;

    if (this.currentCliMode === 'user') promptEl.textContent = `${name}>`;
    else if (this.currentCliMode === 'priv') promptEl.textContent = `${name}#`;
    else if (this.currentCliMode === 'config') promptEl.textContent = `${name}(config)#`;
    else if (this.currentCliMode === 'config-if') promptEl.textContent = `${name}(config-if)#`;
    else promptEl.textContent = `${name}#`;
  }

  async handleRunPing() {
    const srcId = document.getElementById('select-ping-src').value;
    const tgtId = document.getElementById('select-ping-tgt').value;
    const resBox = document.getElementById('ping-results-box');
    if (!srcId || !tgtId) return;

    resBox.style.display = 'block';
    resBox.innerHTML = '<span style="color: var(--text-muted); font-size: 0.75rem;">Simulando transmisión ICMP...</span>';

    try {
      const res = await ApiClient.runPingSimulation(srcId, tgtId);
      const isSuccess = res.success;

      let hopsHtml = '';
      res.hops.forEach(h => {
        hopsHtml += `
          <div class="ping-hop-item ${h.status}">
            <strong>Paso ${h.step} [${h.device_name}]:</strong> ${this.escapeHtml(h.message)}
          </div>
        `;
      });

      resBox.innerHTML = `
        <div class="ping-status-banner ${isSuccess ? 'success' : 'failure'}">
          ${isSuccess ? '✅ Ping Exitoso (ICMP Echo Reply Recibido)' : '❌ Fallo de Conectividad: ' + this.escapeHtml(res.failure_reason || '')}
        </div>
        <div style="font-size: 0.6875rem; color: var(--text-secondary); margin-top: 2px;">
          Ruta: ${this.escapeHtml(res.source_device)} (${res.source_ip}) ➔ ${this.escapeHtml(res.target_device)} (${res.target_ip})
        </div>
        <div class="ping-hop-list">${hopsHtml}</div>
      `;

      // Resaltar la ruta recorrida por el Ping en el lienzo SVG
      if (res.path_links && res.path_links.length) {
        this.topologyViewer.highlightPingPath(res.path_links, isSuccess);
      }
    } catch (e) {
      resBox.innerHTML = `<div class="ping-status-banner failure">Error: ${this.escapeHtml(e.message)}</div>`;
    }
  }

  async handleExecuteCliCommand() {
    const cliInput = document.getElementById('cli-input-command');
    const cliSelect = document.getElementById('select-cli-device');
    const cliOutput = document.getElementById('cli-output');
    const promptEl = document.getElementById('cli-prompt');

    const cmd = cliInput.value.trim();
    const devId = cliSelect.value;
    if (!devId) return;

    if (cmd) {
      this.cliHistory.push(cmd);
      this.cliHistoryIndex = -1;
    }

    const currentPromptText = promptEl.textContent;
    cliInput.value = '';

    // Manejo de limpieza de terminal en el cliente
    if (cmd.toLowerCase() === 'clear' || cmd.toLowerCase() === 'cls') {
      cliOutput.textContent = '';
      return;
    }

    // Escribir comando en el log
    cliOutput.textContent += `\n${currentPromptText} ${cmd}`;

    try {
      const res = await ApiClient.executeCliCommand(
        devId,
        cmd,
        this.currentCliMode,
        this.currentCliInterface
      );

      if (res.output) {
        cliOutput.textContent += `\n${res.output}`;
      }

      this.currentCliMode = res.new_mode;
      this.currentCliInterface = res.current_interface;
      promptEl.textContent = res.prompt;

      cliOutput.scrollTop = cliOutput.scrollHeight;

      // Si la configuración cambió, recargar topología fresca y recalcular diagnósticos en vivo
      if (res.configuration_changed) {
        this.currentTopology = await ApiClient.getTopology();
        await this.refreshDiagnostics();
        if (this.inspectedDeviceId) {
          const updatedDev = this.currentTopology.devices.find(d => d.id === this.inspectedDeviceId);
          if (updatedDev) this.showDeviceDetails(updatedDev);
        }
      }
    } catch (e) {
      cliOutput.textContent += `\n% Error: ${e.message}`;
    }
  }

  generateEvaluationReport() {
    const area = document.getElementById('report-printable-area');
    if (!area || !this.currentTopology || !this.currentReport) return;

    const dateStr = new Date().toLocaleString();
    const rep = this.currentReport;
    const topo = this.currentTopology;

    let findingsRows = '';
    if (rep.findings.length === 0) {
      findingsRows = `<tr><td colspan="5" style="text-align: center; color: var(--status-success); font-weight: 600;">✅ ¡Excelente! La red superó el 100% de las pruebas deterministas sin fallas.</td></tr>`;
    } else {
      rep.findings.forEach((f, idx) => {
        findingsRows += `
          <tr>
            <td style="font-family: var(--font-mono); font-weight: 600;">#${idx+1}</td>
            <td><strong style="color: ${f.severity === 'error' ? 'var(--status-error)' : 'var(--status-warning)'};">[${f.layer}] ${f.severity.toUpperCase()}</strong></td>
            <td><strong>${this.escapeHtml(f.device_name)}</strong> ${f.interface_name ? '('+this.escapeHtml(f.interface_name)+')' : ''}</td>
            <td>${this.escapeHtml(f.title)}<br><small style="color: var(--text-secondary);">${this.escapeHtml(f.description)}</small></td>
            <td style="font-family: var(--font-mono); font-size: 0.6875rem;">${this.escapeHtml(f.technical_solution)}</td>
          </tr>
        `;
      });
    }

    area.innerHTML = `
      <div class="report-header-section">
        <div>
          <h2 style="font-size: 1.15rem; color: var(--text-primary); font-weight: 700;">NetTutorIA — Reporte de Evaluación Técnica</h2>
          <p style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 2px;">Laboratorio Inteligente de Redes y Tutoría Socrática</p>
        </div>
        <div style="text-align: right; font-size: 0.75rem; color: var(--text-secondary);">
          <div><strong>Fecha:</strong> ${dateStr}</div>
          <div><strong>Práctica:</strong> ${this.escapeHtml(topo.name)}</div>
        </div>
      </div>

      <div class="report-kpi-grid">
        <div class="report-kpi-item">
          <div class="num" style="color: var(--brand-primary);">${rep.score_percentage}%</div>
          <div style="font-size: 0.6875rem; color: var(--text-secondary);">Calificación</div>
        </div>
        <div class="report-kpi-item">
          <div class="num" style="color: var(--status-error);">${rep.errors_count}</div>
          <div style="font-size: 0.6875rem; color: var(--text-secondary);">Errores L1/L2/L3</div>
        </div>
        <div class="report-kpi-item">
          <div class="num" style="color: var(--status-warning);">${rep.warnings_count}</div>
          <div style="font-size: 0.6875rem; color: var(--text-secondary);">Advertencias</div>
        </div>
        <div class="report-kpi-item">
          <div class="num" style="color: var(--text-primary);">${topo.devices.length}</div>
          <div style="font-size: 0.6875rem; color: var(--text-secondary);">Dispositivos</div>
        </div>
      </div>

      <div class="report-section-title">Resumen de Inconsistencias y Soluciones Recomendadas</div>
      <table class="report-findings-table">
        <thead>
          <tr>
            <th style="width: 30px;">Item</th>
            <th style="width: 80px;">Severidad</th>
            <th style="width: 120px;">Dispositivo</th>
            <th>Diagnóstico Técnico</th>
            <th style="width: 220px;">Solución / Comandos IOS</th>
          </tr>
        </thead>
        <tbody>
          ${findingsRows}
        </tbody>
      </table>
    `;
  }

  async refreshDiagnostics() {
    try {
      this.currentReport = await ApiClient.runDiagnostics();
      
      // Actualizar visualizador y paneles
      this.topologyViewer.render(this.currentTopology, this.currentReport.findings);
      this.diagnosticsPanel.render(this.currentReport);

      // Actualizar score e indicadores
      this.scoreVal.textContent = `${this.currentReport.score_percentage}%`;
      const errs = this.currentReport.errors_count;
      const warns = this.currentReport.warnings_count;
      this.issuesSummary.textContent = `${errs} error${errs === 1 ? '' : 'es'} · ${warns} advertencia${warns === 1 ? '' : 's'}`;

      // Contador en la pestaña de diagnósticos
      const tabBadge = document.getElementById('diag-tab-badge');
      if (tabBadge) {
        tabBadge.textContent = this.currentReport.total_issues;
        if (this.currentReport.total_issues === 0) {
          tabBadge.classList.add('zero');
        } else {
          tabBadge.classList.remove('zero');
        }
      }
    } catch (e) {
      console.error('Error en diagnóstico:', e);
    }
  }

  askTutorAboutFinding(finding) {
    document.querySelector('[data-tab="tutor"]').click();
    this.tutorChat.setSelectedFinding(finding);
    this.topologyViewer.highlightDevices([finding.device_id]);
  }

  showDeviceDetails(dev) {
    this.inspectedDeviceId = dev.id;
    const inspectCliBtn = document.getElementById('btn-inspect-open-cli');
    if (inspectCliBtn) {
      const isCisco = dev.type === 'router' || dev.type === 'switch';
      inspectCliBtn.style.display = isCisco ? 'inline-flex' : 'none';
    }
    this.inspectTitle.innerHTML = `<span>${this.escapeHtml(dev.name)}</span> <span class="inspect-title-badge">${dev.type.toUpperCase()}</span>`;
    this.inspectTbody.innerHTML = '';

    dev.interfaces.forEach(iface => {
      const tr = document.createElement('tr');
      const ipText = iface.ip_address ? `${iface.ip_address} / ${iface.subnet_mask || ''}` : '—';
      
      let modeText = '—';
      if (iface.encapsulation_dot1q) {
        modeText = `dot1q (VLAN ${iface.encapsulation_dot1q})`;
      } else if (iface.switchport_mode === 'trunk') {
        const allowed = iface.trunk_allowed_vlans ? ` [Allowed: ${iface.trunk_allowed_vlans.join(',')}]` : '';
        modeText = `trunk (Native ${iface.native_vlan || 1})${allowed}`;
      } else if (iface.switchport_mode !== 'none') {
        modeText = `${iface.switchport_mode} (VLAN ${iface.access_vlan || 1})`;
      }

      const isUp = iface.status === 'up';
      const statusColor = isUp ? 'var(--status-success)' : 'var(--status-error)';

      tr.innerHTML = `
        <td style="font-weight: 600; color: var(--text-primary);">${this.escapeHtml(iface.name)}</td>
        <td>${this.escapeHtml(ipText)}</td>
        <td>${this.escapeHtml(modeText)}</td>
        <td><span style="color: ${statusColor}; font-weight: 600;">${this.escapeHtml(iface.status)}</span></td>
      `;
      this.inspectTbody.appendChild(tr);
    });

    if (dev.default_gateway) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td colspan="4" style="color: var(--brand-primary); font-weight: 600; background: var(--bg-surface-subtle);">
          Default Gateway: ${this.escapeHtml(dev.default_gateway)}
        </td>
      `;
      this.inspectTbody.appendChild(tr);
    }

    this.inspectPanel.classList.add('active');
  }

  async checkPacketTracer() {
    const status = await ApiClient.checkPacketTracerStatus();
    if (status.is_active) {
      this.ptStatusDot.classList.add('active');
      this.ptStatusText.textContent = `PT Conectado (${status.pt_ipc_port})`;
    } else {
      this.ptStatusDot.classList.remove('active');
      this.ptStatusText.textContent = 'PT Desconectado';
    }
  }

  async handleImportConfig() {
    const text = document.getElementById('import-config-text').value.trim();
    if (!text) {
      alert('Por favor pega el contenido de show running-config');
      return;
    }

    try {
      const res = await ApiClient.importCiscoConfig(text);
      document.getElementById('modal-import').classList.remove('active');
      document.getElementById('import-config-text').value = '';
      await this.loadApp();
    } catch (e) {
      alert('Error importando: ' + e.message);
    }
  }

  async handleUploadPkt(file) {
    const reader = new FileReader();
    reader.onload = async (ev) => {
      try {
        const loadedTopo = await ApiClient.uploadPktFile(file.name, ev.target.result);
        this.currentTopology = loadedTopo;
        this.labTitle.textContent = loadedTopo.name;
        this.labDesc.textContent = loadedTopo.description || 'Topología activa de red';
        this.resetLabUIState();
        this.topologyViewer.resetView();
        await this.refreshDiagnostics();
        this.populateToolSelectors();
        this.announceLoadedLab();
      } catch (err) {
        alert('Error al procesar el archivo .pkt: ' + err.message);
      }
    };
    reader.readAsDataURL(file);
  }
}

// Inicializar al cargar la página
window.addEventListener('DOMContentLoaded', () => {
  const app = new NetTutorApp();
  app.start();
});

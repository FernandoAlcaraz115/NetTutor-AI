import { ApiClient } from './api.js';
import { TopologyViewer } from './topology_viewer.js';
import { TutorChat } from './tutor_chat.js';
import { DiagnosticsPanel } from './diagnostics_panel.js';

class NetTutorApp {
  constructor() {
    this.currentTopology = null;
    this.currentReport = null;

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
    });

    // Modal Importar Config
    const modal = document.getElementById('modal-import');
    document.getElementById('btn-open-import').addEventListener('click', () => {
      modal.classList.add('active');
    });
    document.getElementById('btn-close-import').addEventListener('click', () => {
      modal.classList.remove('active');
    });
    document.getElementById('btn-submit-import').addEventListener('click', () => {
      this.handleImportConfig();
    });

    // Selector de Prácticas
    document.getElementById('select-lab').addEventListener('change', async (e) => {
      const presetId = e.target.value;
      try {
        await ApiClient.loadPreset(presetId);
        await this.loadApp();
      } catch (err) {
        alert('Error al cargar la práctica: ' + err.message);
      }
    });
  }

  async start() {
    await this.loadApp();
    this.checkPacketTracer();
    // Bienvenida del Tutor
    this.tutorChat.addTutorMessage(
      "👋 ¡Hola! Soy **NetTutor**, tu asistente inteligente para prácticas de redes.\n\n" +
      "He cargado la práctica de **Inter-VLAN Routing**. En esta topología, PC1 (VLAN 10) y PC2 (VLAN 20) deberían poder comunicarse a través del Router R1.\n\n" +
      "🔍 Ya analicé la red y detecté algunos problemas que impiden la conectividad. ¿En qué te puedo ayudar o prefieres que revisemos el primer hallazgo?"
    );
  }

  async loadApp() {
    try {
      this.currentTopology = await ApiClient.getTopology();
      this.labTitle.textContent = this.currentTopology.name;
      this.labDesc.textContent = this.currentTopology.description || '';

      await this.refreshDiagnostics();
    } catch (e) {
      console.error('Error cargando topología:', e);
    }
  }

  async refreshDiagnostics() {
    try {
      this.currentReport = await ApiClient.runDiagnostics();
      
      // Actualizar visualizador y paneles
      this.topologyViewer.render(this.currentTopology, this.currentReport.findings);
      this.diagnosticsPanel.render(this.currentReport);

      // Actualizar score e indicadores
      this.scoreVal.textContent = `${this.currentReport.score_percentage}%`;
      this.issuesSummary.textContent = `${this.currentReport.errors_count} Errores · ${this.currentReport.warnings_count} Advertencias`;

      // Contador en la pestaña de diagnósticos
      const tabBadge = document.getElementById('diag-tab-badge');
      if (tabBadge) {
        tabBadge.textContent = this.currentReport.total_issues;
      }
    } catch (e) {
      console.error('Error en diagnóstico:', e);
    }
  }

  askTutorAboutFinding(finding) {
    // Cambiar a la pestaña de Tutor
    document.querySelector('[data-tab="tutor"]').click();
    this.tutorChat.setSelectedFinding(finding);
    this.topologyViewer.highlightDevices([finding.device_id]);
  }

  showDeviceDetails(dev) {
    this.inspectTitle.textContent = `${dev.name} (${dev.type.toUpperCase()})`;
    this.inspectTbody.innerHTML = '';

    dev.interfaces.forEach(iface => {
      const tr = document.createElement('tr');
      const ipText = iface.ip_address ? `${iface.ip_address} / ${iface.subnet_mask || ''}` : 'Sin asignar';
      const modeText = iface.encapsulation_dot1q 
        ? `dot1q (VLAN ${iface.encapsulation_dot1q})` 
        : (iface.switchport_mode !== 'none' ? `${iface.switchport_mode} (VLAN ${iface.access_vlan || 1})` : '-');

      tr.innerHTML = `
        <td style="color: var(--text-primary); font-weight: 600;">${iface.name}</td>
        <td>${ipText}</td>
        <td>${modeText}</td>
        <td><span style="color: ${iface.status === 'up' ? 'var(--accent-green)' : 'var(--accent-red)'}; font-weight: 600;">${iface.status}</span></td>
      `;
      this.inspectTbody.appendChild(tr);
    });

    if (dev.default_gateway) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td colspan="4" style="color: var(--accent-cyan); font-weight: 600;">Default Gateway: ${dev.default_gateway}</td>
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
      this.ptStatusText.textContent = 'PT No Detectado';
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
      alert(res.message);
      document.getElementById('modal-import').classList.remove('active');
      document.getElementById('import-config-text').value = '';
      await this.loadApp();
    } catch (e) {
      alert('Error importando: ' + e.message);
    }
  }
}

// Inicializar al cargar la página
window.addEventListener('DOMContentLoaded', () => {
  const app = new NetTutorApp();
  app.start();
});

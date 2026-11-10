/**
 * Panel de Diagnóstico Técnico de NetTutorIA (Enterprise SaaS Style)
 */
export class DiagnosticsPanel {
  constructor(containerElement, onAskTutorAboutFinding) {
    this.container = containerElement;
    this.onAskTutor = onAskTutorAboutFinding;
  }

  render(report) {
    this.container.innerHTML = '';

    if (!report || !report.findings || report.findings.length === 0) {
      this.container.innerHTML = `
        <div class="diag-kpi-bar">
          <div class="diag-kpi-card errors">
            <span class="diag-kpi-value">0</span>
            <span class="diag-kpi-label">Errores</span>
          </div>
          <div class="diag-kpi-card warnings">
            <span class="diag-kpi-value">0</span>
            <span class="diag-kpi-label">Advertencias</span>
          </div>
          <div class="diag-kpi-card score">
            <span class="diag-kpi-value">100%</span>
            <span class="diag-kpi-label">Consistencia</span>
          </div>
        </div>
        <div class="empty-diagnostics-box">
          <div class="empty-icon">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
          </div>
          <div class="empty-title">Red 100% Consistente</div>
          <p class="empty-subtitle">No se detectaron inconsistencias en enlaces, subredes o modos de puerto en esta práctica.</p>
        </div>
      `;
      return;
    }

    // Barra de KPIs superior
    const kpiBar = document.createElement('div');
    kpiBar.className = 'diag-kpi-bar';
    kpiBar.innerHTML = `
      <div class="diag-kpi-card errors">
        <span class="diag-kpi-value">${report.errors_count}</span>
        <span class="diag-kpi-label">Errores</span>
      </div>
      <div class="diag-kpi-card warnings">
        <span class="diag-kpi-value">${report.warnings_count}</span>
        <span class="diag-kpi-label">Advertencias</span>
      </div>
      <div class="diag-kpi-card score">
        <span class="diag-kpi-value">${report.score_percentage}%</span>
        <span class="diag-kpi-label">Consistencia</span>
      </div>
    `;
    this.container.appendChild(kpiBar);

    // Lista de tarjetas de hallazgos
    report.findings.forEach(finding => {
      const card = document.createElement('div');
      card.className = `finding-card ${finding.severity}`;
      const locationInfo = `${finding.device_name}${finding.interface_name ? ' : ' + finding.interface_name : ''}`;

      card.innerHTML = `
        <div class="finding-header">
          <div class="finding-badges">
            <span class="finding-pill ${finding.severity}">[${finding.layer}] ${finding.severity.toUpperCase()}</span>
            <span class="finding-device-tag">${locationInfo}</span>
          </div>
        </div>
        <div class="finding-title">${this.escapeHtml(finding.title)}</div>
        <div class="finding-desc">${this.escapeHtml(finding.description)}</div>
        <button class="finding-ask-btn" type="button">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"></circle>
            <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path>
            <line x1="12" y1="17" x2="12.01" y2="17"></line>
          </svg>
          Consultar pista socrática
        </button>
      `;

      card.querySelector('.finding-ask-btn').addEventListener('click', (e) => {
        e.stopPropagation();
        if (this.onAskTutor) {
          this.onAskTutor(finding);
        }
      });

      this.container.appendChild(card);
    });
  }

  escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }
}

/**
 * Panel de Diagnóstico Técnico de NetTutorIA
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
        <div style="padding: 24px; text-align: center; color: var(--text-secondary);">
          <div style="font-size: 3rem; margin-bottom: 12px;">✅</div>
          <h3 style="color: var(--text-primary); margin-bottom: 6px;">¡Sin problemas detectados!</h3>
          <p style="font-size: 0.85rem;">Todas las reglas de consistencia de enlaces, subredes y modos de puerto están superadas.</p>
        </div>
      `;
      return;
    }

    report.findings.forEach(finding => {
      const card = document.createElement('div');
      card.className = `finding-card ${finding.severity}`;
      card.innerHTML = `
        <div class="finding-header">
          <span class="finding-pill ${finding.severity}">[${finding.layer}] ${finding.severity.toUpperCase()}</span>
          <span style="font-size: 0.75rem; color: var(--text-muted); font-family: var(--font-mono);">${finding.device_name}${finding.interface_name ? ' : ' + finding.interface_name : ''}</span>
        </div>
        <div class="finding-title">${finding.title}</div>
        <div class="finding-desc">${finding.description}</div>
        <button class="finding-ask-btn">
          💡 Consultar pista socrática
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
}

/**
 * Cliente de comunicación con la API de NetTutorIA (FastAPI)
 */
const API_BASE = '/api/v1';

export const ApiClient = {
  async getTopology() {
    const res = await fetch(`${API_BASE}/topology`);
    if (!res.ok) throw new Error('Error al obtener la topología');
    return await res.json();
  },

  async runDiagnostics() {
    const res = await fetch(`${API_BASE}/diagnostics/run`, { method: 'POST' });
    if (!res.ok) throw new Error('Error al ejecutar diagnósticos');
    return await res.json();
  },

  async sendTutorChat(userMessage, hintLevel = 1, selectedFindingId = null, chatHistory = []) {
    const res = await fetch(`${API_BASE}/tutor/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_message: userMessage,
        hint_level: hintLevel,
        selected_finding_id: selectedFindingId,
        chat_history: chatHistory
      })
    });
    if (!res.ok) throw new Error('Error al consultar al tutor');
    return await res.json();
  },

  async checkPacketTracerStatus() {
    try {
      const res = await fetch(`${API_BASE}/packet-tracer/status`);
      return await res.json();
    } catch (e) {
      return { is_active: false, message: 'Servicio backend no disponible' };
    }
  },

  async loadPreset(presetId) {
    const res = await fetch(`${API_BASE}/topology/presets/${presetId}/load`, { method: 'POST' });
    if (!res.ok) throw new Error('Error al cargar la práctica');
    return await res.json();
  },

  async importCiscoConfig(configText) {
    const res = await fetch(`${API_BASE}/topology/import-config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ config_text: configText })
    });
    if (!res.ok) throw new Error('Error al importar configuración');
    return await res.json();
  }
};

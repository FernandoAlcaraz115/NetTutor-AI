/**
 * Componente del Chat Socrático del Tutor Inteligente (NetTutor)
 * Estilo Enterprise SaaS / Asistente Técnico
 */
import { ApiClient } from './api.js';

export class TutorChat {
  constructor(messagesContainer, inputElement, sendBtn, onHighlightDevices) {
    this.messagesContainer = messagesContainer;
    this.input = inputElement;
    this.sendBtn = sendBtn;
    this.onHighlightDevices = onHighlightDevices;

    this.currentHintLevel = 1;
    this.selectedFinding = null;
    this.chatHistory = [];

    this.initEvents();
  }

  initEvents() {
    this.sendBtn.addEventListener('click', () => this.handleSendMessage());
    this.input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') this.handleSendMessage();
    });

    // Botones de nivel de pista
    document.querySelectorAll('.btn-hint').forEach(btn => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('.btn-hint').forEach(b => b.classList.remove('active'));
        e.currentTarget.classList.add('active');
        this.currentHintLevel = parseInt(e.currentTarget.dataset.level, 10);
      });
    });
  }

  setHintLevel(level) {
    this.currentHintLevel = level;
    document.querySelectorAll('.btn-hint').forEach(b => {
      b.classList.toggle('active', parseInt(b.dataset.level, 10) === level);
    });
  }

  resetContext() {
    this.selectedFinding = null;
    this.chatHistory = [];
  }

  setSelectedFinding(finding) {
    this.selectedFinding = finding;
    this.addSystemMessage(`Enfocando tutoría en: <strong>${this.escapeHtml(finding.title)}</strong> (${this.escapeHtml(finding.device_name)})`);
    this.triggerTutorQuery(`¿Me puedes orientar sobre el problema detectado en ${finding.device_name}?`);
  }

  async triggerTutorQuery(userPrompt) {
    this.addUserMessage(userPrompt);
    await this.fetchTutorReply(userPrompt);
  }

  async handleSendMessage() {
    const text = this.input.value.trim();
    if (!text) return;
    this.input.value = '';

    this.addUserMessage(text);
    await this.fetchTutorReply(text);
  }

  async fetchTutorReply(userText) {
    const loadingId = this.addLoadingMessage();

    try {
      const response = await ApiClient.sendTutorChat(
        userText,
        this.currentHintLevel,
        this.selectedFinding ? this.selectedFinding.id : null,
        this.chatHistory
      );

      this.removeMessage(loadingId);
      this.addTutorMessage(response.tutor_reply);

      // Resaltar equipos sugeridos en la topología
      if (response.highlight_devices && this.onHighlightDevices) {
        this.onHighlightDevices(response.highlight_devices);
      }
    } catch (e) {
      this.removeMessage(loadingId);
      this.addTutorMessage("⚠️ No fue posible conectar con el servicio de tutoría. Verifica que el servidor backend de NetTutorIA esté en ejecución.");
    }
  }

  addUserMessage(text) {
    this.chatHistory.push({ role: 'user', content: text });
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble user';
    bubble.textContent = text;
    this.messagesContainer.appendChild(bubble);
    this.scrollToBottom();
  }

  addTutorMessage(markdownText) {
    this.chatHistory.push({ role: 'tutor', content: markdownText });
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble tutor';
    bubble.innerHTML = this.renderMarkdown(markdownText);
    this.messagesContainer.appendChild(bubble);
    this.scrollToBottom();
  }

  addSystemMessage(htmlText) {
    const div = document.createElement('div');
    div.className = 'chat-system-tag';
    div.innerHTML = htmlText;
    this.messagesContainer.appendChild(div);
    this.scrollToBottom();
  }

  addLoadingMessage() {
    const id = `loading-${Date.now()}`;
    const bubble = document.createElement('div');
    bubble.id = id;
    bubble.className = 'chat-bubble tutor';
    bubble.innerHTML = '<span style="color: var(--text-muted); font-size: 0.75rem;">NetTutor analizando contexto...</span>';
    this.messagesContainer.appendChild(bubble);
    this.scrollToBottom();
    return id;
  }

  removeMessage(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
  }

  scrollToBottom() {
    this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
  }

  escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  renderMarkdown(text) {
    if (!text) return '';
    // Normalizar saltos de línea Windows y Unix
    let normalized = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

    // 1. Extraer bloques de código multilínea (```cisco ... ```) antes de escapar párrafos
    const codeBlocks = [];
    normalized = normalized.replace(/```(?:cisco|bash|plaintext|sh|json)?\n?([\s\S]*?)```/g, (match, code) => {
      const token = `___PRE_CODE_BLOCK_${codeBlocks.length}___`;
      codeBlocks.push(code.trim());
      return token;
    });

    // 2. Escapar HTML del texto general
    let html = this.escapeHtml(normalized);

    // 3. Formato Markdown inline
    // Código en línea
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Negrita
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    // Cursiva
    html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    // Saltos de línea en texto
    html = html.replace(/\n\n/g, '<br><br>').replace(/\n/g, '<br>');

    // 4. Reinsertar bloques de código limpios y coloreables
    codeBlocks.forEach((code, idx) => {
      const safeCode = this.escapeHtml(code);
      html = html.replace(
        `___PRE_CODE_BLOCK_${idx}___`,
        `<pre class="chat-code-block"><code>${safeCode}</code></pre>`
      );
    });

    return html;
  }
}

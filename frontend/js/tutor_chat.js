/**
 * Componente del Chat Socrático del Tutor Inteligente (NetTutor)
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

  setSelectedFinding(finding) {
    this.selectedFinding = finding;
    this.addSystemMessage(`Enfocando tutoría en: **${finding.title}** (${finding.device_name})`);
    this.triggerTutorQuery(`¿Me puedes dar una pista sobre el problema en ${finding.device_name}?`);
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
      this.addTutorMessage("⚠️ Hubo un inconveniente al consultar al tutor. Asegúrate de que el backend de NetTutorIA esté corriendo.");
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

  addSystemMessage(text) {
    const div = document.createElement('div');
    div.style.fontSize = '0.75rem';
    div.style.color = 'var(--accent-cyan)';
    div.style.textAlign = 'center';
    div.style.margin = '4px 0';
    div.innerHTML = this.renderMarkdown(text);
    this.messagesContainer.appendChild(div);
    this.scrollToBottom();
  }

  addLoadingMessage() {
    const id = `loading-${Date.now()}`;
    const bubble = document.createElement('div');
    bubble.id = id;
    bubble.className = 'chat-bubble tutor';
    bubble.innerHTML = '<span style="color: var(--text-muted); font-style: italic;">NetTutor analizando la práctica...</span>';
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

  renderMarkdown(text) {
    let html = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    // Bloques de código con pre y code
    html = html.replace(/```(?:cisco|bash|plaintext)?\n([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
    // Código en línea
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Negrita
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    // Cursiva
    html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    // Saltos de línea
    html = html.replace(/\n\n/g, '<br><br>').replace(/\n/g, '<br>');

    return html;
  }
}

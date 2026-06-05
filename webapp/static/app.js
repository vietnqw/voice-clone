function openSidebar() {
  document.getElementById('sidebar').classList.add('sidebar-open');
  document.getElementById('sidebar-overlay').classList.remove('hidden');
}
function closeSidebar() {
  document.getElementById('sidebar').classList.remove('sidebar-open');
  document.getElementById('sidebar-overlay').classList.add('hidden');
}
function toggleSidebar() {
  document.getElementById('sidebar').classList.contains('sidebar-open')
    ? closeSidebar()
    : openSidebar();
}

const NONVERBAL_TAGS = [
  { label: 'Cười', tag: '[laughter]' },
  { label: 'Thở dài', tag: '[sigh]' },
  { label: 'Ngạc nhiên', tag: '[surprise-ah]' },
  { label: 'Hỏi', tag: '[question-en]' },
];

function app() {
  return {
    samples: [],
    selectedId: null,
    playingId: null,
    text: '',
    speed: 0.9,
    generating: false,
    audioUrl: null,
    error: null,
    modelReady: false,
    modelError: null,
    nonverbalTags: NONVERBAL_TAGS,
    _healthTimer: null,

    modal: {
      open: false,
      isEdit: false,
      editId: null,
      name: '',
      transcript: '',
      audioFile: null,
      audioPreviewUrl: null,
      saving: false,
    },

    deleteDialog: { show: false, id: null, name: '' },

    get selectedSample() {
      return this.samples.find((s) => s.id === this.selectedId) || null;
    },

    get speedLabel() {
      if (this.speed < 0.8) return 'Chậm';
      if (this.speed <= 1.0) return 'Bình thường';
      return 'Nhanh';
    },

    async init() {
      await this.loadSamples();
      this.pollHealth();
    },

    pollHealth() {
      const check = async () => {
        try {
          const r = await fetch('/api/health');
          const data = await r.json();
          if (data.status === 'ready') {
            this.modelReady = true;
            this.modelError = null;
          } else if (data.status === 'error') {
            this.modelError = data.detail || 'Lỗi tải mô hình';
          } else {
            this._healthTimer = setTimeout(check, 3000);
          }
        } catch {
          this._healthTimer = setTimeout(check, 3000);
        }
      };
      check();
    },

    async loadSamples() {
      try {
        const r = await fetch('/api/samples');
        this.samples = await r.json();
        const def = this.samples.find((s) => s.is_default);
        const current = this.samples.find((s) => s.id === this.selectedId);
        if (!current) {
          this.selectedId = def ? def.id : this.samples[0]?.id || null;
        }
      } catch (e) {
        console.error('Failed to load samples', e);
      }
    },

    select(id) {
      this.selectedId = id;
      this.audioUrl = null;
      this.error = null;
      this.stopPreview();
    },

    async setDefault(id) {
      await fetch(`/api/samples/${id}/default`, { method: 'POST' });
      this.samples = this.samples.map((s) => ({ ...s, is_default: s.id === id }));
    },

    openAddModal() {
      this.modal = {
        open: true,
        isEdit: false,
        editId: null,
        name: '',
        transcript: '',
        audioFile: null,
        audioPreviewUrl: null,
        saving: false,
      };
    },

    openEditModal(sample) {
      this.modal = {
        open: true,
        isEdit: true,
        editId: sample.id,
        name: sample.name,
        transcript: sample.transcript,
        audioFile: null,
        audioPreviewUrl: null,
        saving: false,
      };
    },

    closeModal() {
      if (this.modal.audioPreviewUrl) URL.revokeObjectURL(this.modal.audioPreviewUrl);
      this.modal.open = false;
    },

    handleAudioFile(event) {
      const file = event.target.files[0];
      if (!file) return;
      if (this.modal.audioPreviewUrl) URL.revokeObjectURL(this.modal.audioPreviewUrl);
      this.modal.audioFile = file;
      this.modal.audioPreviewUrl = URL.createObjectURL(file);
    },

    get canSaveModal() {
      const m = this.modal;
      if (!m.name.trim() || !m.transcript.trim()) return false;
      if (!m.isEdit && !m.audioFile) return false;
      return true;
    },

    async saveModal() {
      if (!this.canSaveModal || this.modal.saving) return;
      this.modal.saving = true;
      try {
        if (this.modal.isEdit) {
          const r = await fetch(`/api/samples/${this.modal.editId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: this.modal.name, transcript: this.modal.transcript }),
          });
          if (!r.ok) throw new Error((await r.json()).detail);
          if (this.modal.audioFile) {
            const form = new FormData();
            form.append('audio', this.modal.audioFile);
            const r2 = await fetch(`/api/samples/${this.modal.editId}/audio`, {
              method: 'PUT',
              body: form,
            });
            if (!r2.ok) throw new Error((await r2.json()).detail);
          }
        } else {
          const form = new FormData();
          form.append('name', this.modal.name);
          form.append('transcript', this.modal.transcript);
          form.append('audio', this.modal.audioFile);
          const r = await fetch('/api/samples', { method: 'POST', body: form });
          if (!r.ok) throw new Error((await r.json()).detail);
        }
        await this.loadSamples();
        this.closeModal();
      } catch (e) {
        alert('Lỗi: ' + (e.message || 'Không thể lưu'));
      } finally {
        this.modal.saving = false;
      }
    },

    confirmDelete(sample) {
      this.deleteDialog = { show: true, id: sample.id, name: sample.name };
    },

    async doDelete() {
      const id = this.deleteDialog.id;
      this.deleteDialog.show = false;
      try {
        await fetch(`/api/samples/${id}`, { method: 'DELETE' });
        if (this.selectedId === id) {
          this.audioUrl = null;
          this.error = null;
          this.selectedId = null;
        }
        await this.loadSamples();
      } catch (e) {
        alert('Không thể xóa: ' + e.message);
      }
    },

    stopPreview() {
      if (!this.playingId) return;
      const el = this.$refs.previewPlayer;
      el.pause();
      el.currentTime = 0;
      this.playingId = null;
    },

    previewSample(id) {
      const el = this.$refs.previewPlayer;
      // Toggle off if same card
      if (this.playingId === id) {
        this.stopPreview();
        return;
      }
      // Stop whatever was playing before
      el.pause();
      el.currentTime = 0;
      this.playingId = id;
      el.src = `/api/samples/${id}/audio`;
      el.onended = () => { this.playingId = null; };
      el.play().catch(() => { this.playingId = null; });
    },

    insertTag(tag) {
      const el = this.$refs.textInput;
      const start = el.selectionStart;
      const end = el.selectionEnd;
      this.text = this.text.slice(0, start) + tag + this.text.slice(end);
      // Restore cursor after the inserted tag
      this.$nextTick(() => {
        el.focus();
        el.setSelectionRange(start + tag.length, start + tag.length);
      });
    },

    async generate() {
      if (this.generating || !this.modelReady) return;
      if (!this.text.trim()) {
        this.error = 'Vui lòng nhập văn bản';
        return;
      }
      if (!this.selectedId) {
        this.error = 'Vui lòng chọn giọng mẫu';
        return;
      }
      this.generating = true;
      this.error = null;
      if (this.audioUrl) {
        URL.revokeObjectURL(this.audioUrl);
        this.audioUrl = null;
      }
      try {
        const r = await fetch('/api/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: this.text,
            sample_id: this.selectedId,
            speed: this.speed,
          }),
        });
        if (!r.ok) {
          const err = await r.json();
          throw new Error(err.detail || 'Lỗi không xác định');
        }
        const blob = await r.blob();
        this.audioUrl = URL.createObjectURL(blob);
      } catch (e) {
        this.error = e.message;
      } finally {
        this.generating = false;
      }
    },
  };
}

/* ==========================================================================
   SmartCompress Pro - upload.js
   Animated drag & drop uploader with validation and chunked uploads.
   ========================================================================== */
(function () {
    'use strict';

    const IMAGE_EXT = ['jpg', 'jpeg', 'png', 'webp', 'bmp', 'gif', 'tiff'];
    const DOC_EXT = ['pdf', 'docx', 'xlsx', 'pptx'];
    const CHUNK_THRESHOLD = 40 * 1024 * 1024; // 40 MB
    const CHUNK_SIZE = 5 * 1024 * 1024;       // 5 MB per chunk

    function ext(name) {
        const parts = (name || '').split('.');
        return parts.length > 1 ? parts.pop().toLowerCase() : '';
    }

    function uid() {
        return 'u_' + Math.random().toString(36).slice(2) + Date.now().toString(36);
    }

    function iconFor(name) {
        const e = ext(name);
        if (e === 'pdf') return 'fa-solid fa-file-pdf';
        if (e === 'docx') return 'fa-solid fa-file-word';
        if (e === 'xlsx') return 'fa-solid fa-file-excel';
        if (e === 'pptx') return 'fa-solid fa-file-powerpoint';
        return 'fa-solid fa-image';
    }

    class Uploader {
        constructor(root, options) {
            this.root = root;
            this.options = options || {};
            this.uploadUrl = root.dataset.uploadUrl;
            this.chunkUrl = root.dataset.chunkUrl;
            this.mode = root.dataset.mode || 'image';
            this.maxBytes = (parseInt(root.dataset.maxUpload, 10) || 4096) * 1024 * 1024;
            this.allowed = this.mode === 'document' ? DOC_EXT : IMAGE_EXT;
            this.items = [];
            this.dropzone = root.querySelector('#dropzone');
            this.input = root.querySelector('#fileInput');
            this.browseBtn = root.querySelector('#browseBtn');
            this.listEl = root.querySelector('#fileList');
            this.bind();
        }

        bind() {
            const self = this;
            if (this.browseBtn) this.browseBtn.addEventListener('click', function (e) { e.stopPropagation(); self.input.click(); });
            if (this.dropzone) this.dropzone.addEventListener('click', function () { self.input.click(); });
            if (this.input) this.input.addEventListener('change', function () { self.addFiles(self.input.files); self.input.value = ''; });

            ['dragenter', 'dragover'].forEach(function (evt) {
                self.dropzone.addEventListener(evt, function (e) { e.preventDefault(); self.dropzone.classList.add('dragover'); });
            });
            ['dragleave', 'drop'].forEach(function (evt) {
                self.dropzone.addEventListener(evt, function (e) { e.preventDefault(); self.dropzone.classList.remove('dragover'); });
            });
            self.dropzone.addEventListener('drop', function (e) {
                if (e.dataTransfer && e.dataTransfer.files) self.addFiles(e.dataTransfer.files);
            });
        }

        addFiles(fileList) {
            const self = this;
            Array.from(fileList || []).forEach(function (file) {
                const e = ext(file.name);
                if (self.allowed.indexOf(e) === -1) {
                    window.SC.toast('Unsupported file type: ' + file.name, 'error');
                    return;
                }
                if (file.size > self.maxBytes) {
                    window.SC.toast(file.name + ' exceeds the ' + window.SC.formatBytes(self.maxBytes) + ' limit.', 'error');
                    return;
                }
                const item = {
                    id: uid(),
                    file: file,
                    status: 'queued',
                    progress: 0,
                    uploadId: null,
                    record: null
                };
                self.items.push(item);
                self.renderItem(item);
                self.uploadItem(item);
            });
            self.notify();
        }

        renderItem(item) {
            const self = this;
            const el = document.createElement('div');
            el.className = 'file-card animate-pop';
            el.dataset.id = item.id;
            const preview = item.file.type && item.file.type.indexOf('image/') === 0
                ? '<img src="' + URL.createObjectURL(item.file) + '" alt="">'
                : '<i class="' + iconFor(item.file.name) + '"></i>';
            el.innerHTML =
                '<div class="file-thumb">' + preview + '</div>' +
                '<div class="file-info">' +
                    '<h5 class="text-truncate" title="' + item.file.name + '">' + item.file.name + '</h5>' +
                    '<span class="file-meta">' + window.SC.formatBytes(item.file.size) + ' &middot; ' + item.status + '</span>' +
                    '<div class="progress premium-progress slim mt-2" style="display:none"><div class="progress-bar" style="width:0%"></div></div>' +
                '</div>' +
                '<span class="file-badge">' + ext(item.file.name).toUpperCase() + '</span>' +
                '<button type="button" class="file-remove" title="Remove"><i class="fa-solid fa-xmark"></i></button>';
            el.querySelector('.file-remove').addEventListener('click', function () { self.removeItem(item.id); });
            item.el = el;
            if (this.listEl) this.listEl.appendChild(el);
        }

        updateItem(item) {
            if (!item.el) return;
            const meta = item.el.querySelector('.file-meta');
            const bar = item.el.querySelector('.progress');
            if (meta) meta.innerHTML = window.SC.formatBytes(item.file.size) + ' &middot; ' + item.status;
            if (bar) {
                bar.style.display = item.status === 'uploading' ? 'flex' : 'none';
                const fill = bar.querySelector('.progress-bar');
                if (fill) fill.style.width = item.progress + '%';
            }
        }

        removeItem(id) {
            const index = this.items.findIndex(function (i) { return i.id === id; });
            if (index === -1) return;
            const item = this.items[index];
            if (item.el && window.gsap) {
                window.gsap.to(item.el, { opacity: 0, x: 30, duration: .25, onComplete: function () { item.el.remove(); } });
            } else if (item.el) {
                item.el.remove();
            }
            this.items.splice(index, 1);
            this.notify();
        }

        clear() {
            this.items.forEach(function (item) { if (item.el) item.el.remove(); });
            this.items = [];
            this.notify();
        }

        notify() {
            if (this.options.onChange) this.options.onChange(this);
        }

        uploadedIds() {
            return this.items.filter(function (i) { return i.status === 'done' && i.record; }).map(function (i) { return i.record.id; });
        }

        isUploading() {
            return this.items.some(function (i) { return i.status === 'uploading' || i.status === 'queued'; });
        }

        uploadItem(item) {
            const self = this;
            item.status = 'uploading';
            item.progress = 0;
            self.updateItem(item);
            if (item.file.size > CHUNK_THRESHOLD) {
                item.uploadId = uid();
                const total = Math.ceil(item.file.size / CHUNK_SIZE);
                self.uploadChunk(item, 0, total);
            } else {
                self.uploadSimple(item);
            }
        }

        uploadSimple(item) {
            const self = this;
            const form = new FormData();
            form.append('file', item.file);
            const xhr = new XMLHttpRequest();
            xhr.open('POST', this.uploadUrl);
            xhr.setRequestHeader('X-CSRFToken', window.SC.csrf());
            xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
            xhr.upload.onprogress = function (e) {
                if (e.lengthComputable) {
                    item.progress = Math.round((e.loaded / e.total) * 100);
                    self.updateItem(item);
                }
            };
            xhr.onload = function () {
                let data = {};
                try { data = JSON.parse(xhr.responseText); } catch (err) {}
                if (xhr.status >= 200 && xhr.status < 300) {
                    item.record = data;
                    item.status = 'done';
                    item.progress = 100;
                } else {
                    item.status = 'error';
                    window.SC.toast(data.error || ('Upload failed for ' + item.file.name), 'error');
                }
                self.updateItem(item);
                self.notify();
            };
            xhr.onerror = function () {
                item.status = 'error';
                self.updateItem(item);
                self.notify();
                window.SC.toast('Network error while uploading ' + item.file.name, 'error');
            };
            xhr.send(form);
        }

        uploadChunk(item, index, total) {
            const self = this;
            const start = index * CHUNK_SIZE;
            const blob = item.file.slice(start, start + CHUNK_SIZE);
            const form = new FormData();
            form.append('upload_id', item.uploadId);
            form.append('chunk_index', index);
            form.append('total_chunks', total);
            form.append('filename', item.file.name);
            form.append('chunk', blob, item.file.name + '.part');

            const xhr = new XMLHttpRequest();
            xhr.open('POST', this.chunkUrl);
            xhr.setRequestHeader('X-CSRFToken', window.SC.csrf());
            xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
            xhr.onload = function () {
                let data = {};
                try { data = JSON.parse(xhr.responseText); } catch (err) {}
                if (xhr.status >= 200 && xhr.status < 300) {
                    const completed = index + 1;
                    item.progress = Math.round((completed / total) * 100);
                    self.updateItem(item);
                    if (data.id) {
                        item.record = data;
                        item.status = 'done';
                    } else {
                        self.uploadChunk(item, index + 1, total);
                    }
                } else {
                    item.status = 'error';
                    self.updateItem(item);
                    window.SC.toast(data.error || ('Chunk upload failed for ' + item.file.name), 'error');
                }
                self.notify();
            };
            xhr.onerror = function () {
                item.status = 'error';
                self.updateItem(item);
                self.notify();
                window.SC.toast('Network error while uploading ' + item.file.name, 'error');
            };
            item.progress = Math.round((index / total) * 100);
            self.updateItem(item);
            xhr.send(form);
        }
    }

    window.SCUploader = Uploader;
})();

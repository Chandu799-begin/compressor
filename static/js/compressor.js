/* ==========================================================================
   SmartCompress Pro - compressor.js
   Target-size selector, compression requests, live progress and results.
   ========================================================================== */
(function () {
    'use strict';

    let presets = {};
    const scriptEl = document.getElementById('sizePresetsData');
    if (scriptEl) {
        try { presets = JSON.parse(scriptEl.textContent); } catch (e) { presets = {}; }
    }

    function escapeHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function statusClass(status) {
        if (status === 'completed') return 'status-completed';
        if (status === 'warning') return 'status-warning';
        if (status === 'failed') return 'status-failed';
        return 'status-processing';
    }

    function setupWorkspace(root) {
        const state = { unit: 'KB', presetValue: null, level: 'medium', bestEffort: false };

        const unitTabs = root.querySelector('#unitTabs');
        const presetGrid = root.querySelector('#presetGrid');
        const customSize = root.querySelector('#customSize');
        const customUnit = root.querySelector('#customUnit');
        const bestEffortToggle = root.querySelector('#bestEffortToggle');
        const compressBtn = root.querySelector('#compressBtn');
        const clearBtn = root.querySelector('#clearBtn');
        const downloadAllBtn = root.querySelector('#downloadAllBtn');
        const progressCard = root.querySelector('#progressCard');
        const progressBar = root.querySelector('#progressBar');
        const progressLabel = root.querySelector('#progressLabel');
        const resultsGrid = root.querySelector('#resultsGrid');
        const resultsHeader = root.querySelector('#resultsHeader');
        const resultsSummary = root.querySelector('#resultsSummary');

        let uploadedJobs = [];

        function renderPresets() {
            if (!presetGrid) return;
            presetGrid.innerHTML = '';
            (presets[state.unit] || []).forEach(function (preset) {
                const chip = document.createElement('button');
                chip.type = 'button';
                chip.className = 'preset-chip' + (state.presetValue === preset.bytes ? ' active' : '');
                chip.textContent = preset.label;
                chip.addEventListener('click', function () {
                    state.presetValue = preset.bytes;
                    if (customSize) customSize.value = '';
                    renderPresets();
                });
                presetGrid.appendChild(chip);
            });
        }

        if (unitTabs) {
            unitTabs.addEventListener('click', function (e) {
                const tab = e.target.closest('.unit-tab');
                if (!tab) return;
                state.unit = tab.dataset.unit;
                state.presetValue = null;
                if (customUnit) customUnit.value = state.unit;
                unitTabs.querySelectorAll('.unit-tab').forEach(function (t) { t.classList.toggle('active', t === tab); });
                renderPresets();
            });
        }

        if (customSize) {
            customSize.addEventListener('input', function () {
                state.presetValue = null;
                renderPresets();
            });
        }

        root.querySelectorAll('#levelPills .level-pill').forEach(function (pill) {
            pill.addEventListener('click', function () {
                root.querySelectorAll('#levelPills .level-pill').forEach(function (p) { p.classList.remove('active'); });
                pill.classList.add('active');
                const input = pill.querySelector('input');
                input.checked = true;
                state.level = input.value;
            });
        });

        if (bestEffortToggle) {
            bestEffortToggle.addEventListener('change', function () {
                state.bestEffort = bestEffortToggle.checked;
                if (presetGrid) presetGrid.style.opacity = state.bestEffort ? '.45' : '1';
                if (customSize) customSize.disabled = state.bestEffort;
            });
        }

        const uploader = new window.SCUploader(root, {
            onChange: function () { updateButton(); }
        });

        function updateButton() {
            if (!compressBtn) return;
            compressBtn.disabled = uploader.items.length === 0 || uploader.isUploading();
        }

        function resolveTarget() {
            if (state.bestEffort) return { value: null, unit: state.unit };
            if (customSize && customSize.value) return { value: parseFloat(customSize.value), unit: customUnit ? customUnit.value : state.unit };
            if (state.presetValue) {
                const bytes = state.presetValue;
                if (state.unit === 'KB') return { value: bytes / 1024, unit: 'KB' };
                if (state.unit === 'MB') return { value: bytes / (1024 * 1024), unit: 'MB' };
                return { value: bytes / (1024 * 1024 * 1024), unit: 'GB' };
            }
            return { value: null, unit: state.unit };
        }

        function showProgress(visible) {
            if (!progressCard) return;
            progressCard.classList.toggle('d-none', !visible);
        }

        function animateProgress() {
            if (!progressBar || !progressLabel) return;
            progressBar.style.width = '8%';
            progressLabel.textContent = 'Working…';
            let value = 8;
            const timer = setInterval(function () {
                value = Math.min(value + Math.random() * 9, 92);
                progressBar.style.width = value + '%';
            }, 320);
            return function () { clearInterval(timer); };
        }

        if (compressBtn) {
            compressBtn.addEventListener('click', function () {
                const ids = uploader.uploadedIds();
                if (!ids.length) {
                    window.SC.toast('Add at least one file and wait for the upload to finish.', 'error');
                    return;
                }
                const target = resolveTarget();
                const payload = {
                    upload_ids: ids,
                    level: state.level,
                    target_value: target.value,
                    target_unit: target.unit,
                    max_width: valueOf(root, '#maxWidth'),
                    max_height: valueOf(root, '#maxHeight'),
                    keep_aspect: checked(root, '#keepAspect'),
                    strip_metadata: checked(root, '#stripMetadata'),
                    convert_to_webp: false,
                    output_format: valueOf(root, '#outputFormat') || 'auto',
                    downsample: checked(root, '#downsample'),
                    use_ghostscript: checked(root, '#ghostscript')
                };

                compressBtn.disabled = true;
                showProgress(true);
                const stop = animateProgress();

                window.SC.request(root.dataset.compressUrl, { method: 'POST', json: payload })
                    .then(function (data) {
                        stop();
                        if (progressBar) progressBar.style.width = '100%';
                        if (progressLabel) progressLabel.textContent = 'Done';
                        setTimeout(function () { showProgress(false); }, 800);
                        handleResults(data.jobs || []);
                    })
                    .catch(function (error) {
                        stop();
                        showProgress(false);
                        window.SC.toast(error.message, 'error');
                    })
                    .finally(function () { compressBtn.disabled = false; updateButton(); });
            });
        }

        function handleResults(jobs) {
            uploadedJobs = uploadedJobs.concat(jobs);
            if (resultsGrid) {
                jobs.forEach(function (job) { resultsGrid.insertAdjacentHTML('afterbegin', resultCardHtml(job)); });
            }
            if (resultsHeader) resultsHeader.classList.remove('d-none');
            updateSummary();
            updateDownloadAll();
            jobs.filter(function (j) { return j.status === 'pending' || j.status === 'processing'; })
                .forEach(pollJob);
            if (window.gsap && resultsGrid) {
                gsap.from(resultsGrid.querySelectorAll('.result-card'), { y: 20, opacity: 0, duration: .5, stagger: .06 });
            }
        }

        function pollJob(job) {
            const template = root.dataset.statusUrlTemplate || '/api/job/0/status/';
            const url = template.replace('/0/', '/' + job.id + '/');
            const timer = setInterval(function () {
                window.SC.request(url, { method: 'GET' }).then(function (data) {
                    if (data.status !== 'pending' && data.status !== 'processing') {
                        clearInterval(timer);
                        updateCard(data);
                    }
                }).catch(function () { clearInterval(timer); });
            }, 1500);
        }

        function updateCard(job) {
            const card = resultsGrid && resultsGrid.querySelector('[data-job-id="' + job.id + '"]');
            if (!card) return;
            card.outerHTML = resultCardHtml(job);
            const index = uploadedJobs.findIndex(function (j) { return j.id === job.id; });
            if (index !== -1) uploadedJobs[index] = job;
            updateSummary();
            updateDownloadAll();
        }

        function updateSummary() {
            if (!resultsSummary) return;
            const done = uploadedJobs.filter(function (j) { return j.compressed_size; });
            if (!done.length) { resultsSummary.textContent = uploadedJobs.length + ' files'; return; }
            const avg = done.reduce(function (sum, j) { return sum + (j.percentage || 0); }, 0) / done.length;
            resultsSummary.textContent = done.length + ' compressed &middot; ' + avg.toFixed(1) + '% avg'.replace('&middot;', '·');
        }

        function updateDownloadAll() {
            if (!downloadAllBtn) return;
            const ready = uploadedJobs.filter(function (j) { return j.download_url; });
            downloadAllBtn.disabled = ready.length === 0;
        }

        if (downloadAllBtn) {
            downloadAllBtn.addEventListener('click', function () {
                const ids = uploadedJobs.filter(function (j) { return j.download_url; }).map(function (j) { return j.id; });
                if (!ids.length) return;
                fetch(root.dataset.downloadAllUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': window.SC.csrf(),
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify({ job_ids: ids })
                }).then(function (response) {
                    if (!response.ok) throw new Error('Could not build the archive.');
                    return response.blob();
                }).then(function (blob) {
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'smartcompress_pro.zip';
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    URL.revokeObjectURL(url);
                    window.SC.toast('Archive downloaded.', 'success');
                }).catch(function (error) { window.SC.toast(error.message, 'error'); });
            });
        }

        if (clearBtn) {
            clearBtn.addEventListener('click', function () {
                uploader.clear();
                if (resultsGrid) resultsGrid.innerHTML = '';
                uploadedJobs = [];
                if (resultsHeader) resultsHeader.classList.add('d-none');
                updateDownloadAll();
                updateButton();
            });
        }

        renderPresets();
        updateButton();
        updateDownloadAll();
    }

    function valueOf(root, selector) {
        const el = root.querySelector(selector);
        return el && el.value ? el.value : null;
    }

    function checked(root, selector) {
        const el = root.querySelector(selector);
        return el ? el.checked : false;
    }

    function resultCardHtml(job) {
        const icon = fileIcon(job.filename);
        const metrics = job.compressed_size
            ? '' +
                '<div class="metric"><span class="metric-label">Original</span><span class="metric-value">' + escapeHtml(job.original_size_display) + '</span></div>' +
                '<div class="metric"><span class="metric-label">Target</span><span class="metric-value">' + escapeHtml(job.target_size_display) + '</span></div>' +
                '<div class="metric"><span class="metric-label">Compressed</span><span class="metric-value">' + escapeHtml(job.compressed_size_display) + '</span></div>' +
                '<div class="metric accent"><span class="metric-label">Savings</span><span class="metric-value">' + job.percentage + '%</span></div>'
            : '' +
                '<div class="metric"><span class="metric-label">Original</span><span class="metric-value">' + escapeHtml(job.original_size_display) + '</span></div>' +
                '<div class="metric"><span class="metric-label">Target</span><span class="metric-value">' + escapeHtml(job.target_size_display) + '</span></div>';

        const progress = job.compressed_size
            ? '<div class="progress premium-progress slim"><div class="progress-bar" style="width:' + Math.min(job.percentage, 100) + '%"></div></div>'
            : '';

        const compare = (job.preview_url && job.original_url)
            ? '<div class="thumb-compare"><img src="' + job.original_url + '" alt="original"><img src="' + job.preview_url + '" alt="compressed"></div>'
            : '';

        const actions = job.download_url
            ? (job.preview_url ? '<a href="' + job.preview_url + '" target="_blank" class="btn btn-ghost btn-sm"><i class="fa-solid fa-eye me-1"></i>Preview</a>' : '') +
              '<a href="' + job.download_url + '" class="btn btn-glow btn-sm"><i class="fa-solid fa-download me-1"></i>Download</a>'
            : '';

        return '' +
            '<div class="glass result-card animate-pop" data-job-id="' + job.id + '">' +
                '<div class="result-top">' +
                    '<div class="result-type"><i class="' + icon + '"></i></div>' +
                    '<div class="flex-grow-1 min-w-0">' +
                        '<h5 class="text-truncate mb-0" title="' + escapeHtml(job.filename) + '">' + escapeHtml(job.filename) + '</h5>' +
                        '<span class="text-dim small">' + escapeHtml(job.filename.split('.').pop().toUpperCase()) + ' &middot; ' + job.processing_time + 's</span>' +
                    '</div>' +
                    '<span class="status-pill ' + statusClass(job.status) + '">' + escapeHtml(job.status_display) + '</span>' +
                '</div>' +
                compare +
                '<div class="result-metrics">' + metrics + '</div>' +
                progress +
                (job.message ? '<p class="result-message small">' + escapeHtml(job.message) + '</p>' : '') +
                '<div class="result-actions">' + actions +
                    '<a href="' + job.results_url + '" class="btn btn-ghost btn-sm">Details</a>' +
                '</div>' +
            '</div>';
    }

    function fileIcon(name) {
        const e = (name || '').split('.').pop().toLowerCase();
        if (e === 'pdf') return 'fa-solid fa-file-pdf';
        if (e === 'docx') return 'fa-solid fa-file-word';
        if (e === 'xlsx') return 'fa-solid fa-file-excel';
        if (e === 'pptx') return 'fa-solid fa-file-powerpoint';
        return 'fa-solid fa-image';
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-workspace]').forEach(setupWorkspace);
    });
})();

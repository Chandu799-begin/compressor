/* ==========================================================================
   SmartCompress Pro - dashboard.js
   Shared helpers: theme, sidebar, toasts, delete/clear history, compare slider.
   ========================================================================== */
(function () {
    'use strict';

    function getCookie(name) {
        const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]+)'));
        return match ? decodeURIComponent(match[1]) : '';
    }

    function setCookie(name, value, days) {
        const expires = new Date(Date.now() + (days || 365) * 864e5).toUTCString();
        document.cookie = name + '=' + encodeURIComponent(value) + '; expires=' + expires + '; path=/; SameSite=Lax';
    }

    function formatBytes(bytes) {
        bytes = Number(bytes) || 0;
        if (bytes < 1024) return bytes + ' B';
        const units = ['KB', 'MB', 'GB', 'TB'];
        let i = -1;
        do { bytes /= 1024; i++; } while (bytes >= 1024 && i < units.length - 1);
        return bytes.toFixed(2) + ' ' + units[i];
    }

    const SC = {
        csrf: function () {
            const meta = document.querySelector('meta[name="csrf-token"]');
            return (meta && meta.content) || getCookie('csrftoken');
        },
        getCookie: getCookie,
        setCookie: setCookie,
        formatBytes: formatBytes,

        toast: function (message, type, timeout) {
            type = type || 'info';
            const stack = document.getElementById('toastStack');
            if (!stack) return;
            const icons = { success: 'fa-circle-check', error: 'fa-circle-exclamation', info: 'fa-circle-info' };
            const el = document.createElement('div');
            el.className = 'sc-toast ' + type;
            el.innerHTML = '<i class="fa-solid ' + (icons[type] || icons.info) + '"></i><div>' + message + '</div>';
            stack.appendChild(el);
            if (window.gsap) gsap.fromTo(el, { y: 20, opacity: 0 }, { y: 0, opacity: 1, duration: .3 });
            setTimeout(function () {
                if (window.gsap) {
                    gsap.to(el, { y: 16, opacity: 0, duration: .3, onComplete: function () { el.remove(); } });
                } else {
                    el.remove();
                }
            }, timeout || 4200);
        },

        request: function (url, options) {
            options = options || {};
            options.headers = options.headers || {};
            options.headers['X-CSRFToken'] = SC.csrf();
            options.headers['X-Requested-With'] = 'XMLHttpRequest';
            if (options.json) {
                options.headers['Content-Type'] = 'application/json';
                options.body = JSON.stringify(options.json);
                delete options.json;
            }
            return fetch(url, options).then(function (response) {
                const contentType = response.headers.get('content-type') || '';
                const parsed = contentType.indexOf('application/json') !== -1 ? response.json() : response.text();
                return parsed.then(function (data) {
                    if (!response.ok) {
                        const message = (data && data.error) || (typeof data === 'string' ? data : 'Request failed');
                        throw new Error(message);
                    }
                    return data;
                });
            });
        }
    };

    window.SC = SC;

    /* ------------------------------------------------------------- theme */
    function applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        try { localStorage.setItem('sc_theme', theme); } catch (e) {}
        setCookie('pref_theme', theme, 365);
        document.querySelectorAll('.theme-toggle i').forEach(function (icon) {
            icon.className = theme === 'dark' ? 'fa-solid fa-moon' : 'fa-solid fa-sun';
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        applyTheme(document.documentElement.getAttribute('data-theme') || 'dark');
        const toggle = document.getElementById('themeToggle');
        if (toggle) {
            toggle.addEventListener('click', function () {
                const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
                applyTheme(next);
            });
        }

        /* ----------------------------------------------------- sidebar */
        const sidebar = document.getElementById('scSidebar');
        const sidebarToggle = document.getElementById('sidebarToggle');
        if (sidebarToggle && sidebar) {
            sidebarToggle.addEventListener('click', function (e) {
                e.stopPropagation();
                sidebar.classList.toggle('open');
                document.body.classList.toggle('sidebar-open', sidebar.classList.contains('open'));
            });
            document.addEventListener('click', function (e) {
                if (sidebar.classList.contains('open') && !sidebar.contains(e.target) && e.target !== sidebarToggle) {
                    sidebar.classList.remove('open');
                    document.body.classList.remove('sidebar-open');
                }
            });
        }

        /* -------------------------------------------------------- GSAP */
        if (window.gsap) {
            gsap.from('.sc-navbar', { y: -60, opacity: 0, duration: .6, ease: 'power2.out' });
            gsap.utils.toArray('.animate-up').forEach(function (el, i) {
                gsap.fromTo(el, { y: 26, opacity: 0 }, { y: 0, opacity: 1, duration: .7, delay: Math.min(i * .05, .4), ease: 'power2.out' });
            });
        }

        /* ------------------------------------------- delete single job */
        document.addEventListener('click', function (event) {
            const btn = event.target.closest('.delete-job, .delete-job-page');
            if (!btn) return;
            const url = btn.getAttribute('data-delete-url') || ('/job/' + btn.dataset.jobId + '/delete/');
            const card = btn.closest('.result-card');
            SC.request(url, { method: 'POST' }).then(function () {
                SC.toast('Item deleted.', 'success');
                if (card) {
                    if (window.gsap) gsap.to(card, { opacity: 0, scale: .96, duration: .3, onComplete: function () { card.remove(); } });
                    else card.remove();
                } else if (btn.classList.contains('delete-job-page')) {
                    window.location.href = '/dashboard/';
                }
            }).catch(function (error) { SC.toast(error.message, 'error'); });
        });

        /* ---------------------------------------------- clear history */
        const clearBtn = document.getElementById('clearHistoryBtn');
        if (clearBtn && window.scClearUrl) {
            clearBtn.addEventListener('click', function () {
                if (!confirm('Delete all compression history? This cannot be undone.')) return;
                SC.request(window.scClearUrl, { method: 'POST' }).then(function () {
                    SC.toast('History cleared.', 'success');
                    setTimeout(function () { window.location.reload(); }, 600);
                }).catch(function (error) { SC.toast(error.message, 'error'); });
            });
        }

        /* ------------------------------------------ compare slider */
        initCompare();
    });

    function initCompare() {
        const range = document.getElementById('compareRange');
        const after = document.getElementById('compareAfter');
        const handle = document.getElementById('compareHandle');
        if (!range || !after || !handle) return;
        function update(value) {
            after.style.width = value + '%';
            handle.style.left = value + '%';
        }
        update(range.value);
        ['input', 'change'].forEach(function (evt) {
            range.addEventListener(evt, function () { update(range.value); });
        });
    }
})();

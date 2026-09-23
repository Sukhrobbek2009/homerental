// Shared API client. Every page loads this (after config.js) and makes its
// backend calls through apiFetch(), which:
//   - prefixes the path with UR_CONFIG.apiBaseUrl,
//   - sends the stored access token as "Authorization: Bearer ...",
//   - on a 401, discards the stored session and sends the user to /login.
// It also provides the signed-in user (urAuth.getMe) and small helpers for
// showing API errors (urUi).
//
// The only things kept in browser storage are the session tokens and the
// theme preference; everything else, including the user's name and role,
// comes from the API.
(function(){
  // ur-user-name / ur-user-role are no longer written, but are still cleared
  // so sessions from before that change don't leave them behind.
  var AUTH_KEYS = ['ur-access-token', 'ur-refresh-token', 'ur-user-name', 'ur-user-role'];

  // Login/signup legitimately answer 401 for a bad password; the page shows
  // that error itself instead of being bounced back to the login page.
  var NO_REDIRECT_PATHS = ['/api/auth/login', '/api/auth/signup', '/api/auth/google', '/api/auth/refresh'];

  // Site base path ("/homerental" on GitHub Pages, "" locally), passed in on
  // the <script> tag since Jekyll doesn't template this file.
  var script = document.currentScript;
  var siteBase = (script && script.getAttribute('data-site-base')) || '';

  var config = window.UR_CONFIG || {};
  var apiBase = (config.apiBaseUrl || '').replace(/\/+$/, '');

  function apiUrl(path){
    return /^https?:\/\//.test(path) ? path : apiBase + path;
  }

  function getToken(){
    return localStorage.getItem('ur-access-token');
  }

  function clearSession(){
    AUTH_KEYS.forEach(function(key){ localStorage.removeItem(key); });
  }

  function redirectToLogin(){
    var dest = location.pathname + location.search;
    window.location.href = siteBase + '/login?redirect=' + encodeURIComponent(dest);
  }

  function apiFetch(path, options){
    options = options || {};
    var headers = new Headers(options.headers || {});
    var token = getToken();
    if(token && !headers.has('Authorization')){
      headers.set('Authorization', 'Bearer ' + token);
    }

    return fetch(apiUrl(path), Object.assign({}, options, { headers: headers })).catch(function(err){
      console.error('Network error calling ' + path + ':', err);
      throw new Error('Could not reach the server. Please check your connection and try again.');
    }).then(function(res){
      var pathOnly = String(path).split('?')[0];
      if(res.status === 401 && NO_REDIRECT_PATHS.indexOf(pathOnly) === -1){
        clearSession();
        redirectToLogin();
      }
      return res;
    });
  }

  // The signed-in user from /api/auth/me, fetched at most once per page.
  // Resolves to null when logged out or if the request fails.
  var mePromise = null;
  function getMe(){
    if(!getToken()) return Promise.resolve(null);
    if(!mePromise){
      mePromise = apiFetch('/api/auth/me')
        .then(function(res){ return res.ok ? res.json() : null; })
        .catch(function(err){
          console.error('Could not load the signed-in user:', err);
          return null;
        });
    }
    return mePromise;
  }

  function firstName(user){
    var name = ((user && user.full_name) || '').trim();
    return name ? name.split(/\s+/)[0] : '';
  }

  // A user-facing message for a failed response: the server's own detail
  // when it sent one, otherwise a default for the status.
  function errorMessage(res, fallback){
    return res.clone().json().catch(function(){ return null; }).then(function(data){
      var detail = data && data.detail;
      if(typeof detail === 'string' && detail) return detail;
      if(Array.isArray(detail) && detail.length) return detail.map(function(d){ return d.msg; }).join(' ');
      if(res.status === 401) return 'Your session has expired. Please log in again.';
      if(res.status === 403) return "You don't have permission to do that.";
      if(res.status === 409) return 'That conflicts with a recent change. Refresh the page and try again.';
      return fallback || 'Something went wrong. Please try again.';
    });
  }

  // Same, as an Error carrying the status, for `throw await urUi.apiError(res)`.
  function apiError(res, fallback){
    return errorMessage(res, fallback).then(function(message){
      var err = new Error(message);
      err.status = res.status;
      return err;
    });
  }

  var toastStyleAdded = false;
  function addToastStyle(){
    if(toastStyleAdded) return;
    toastStyleAdded = true;
    var style = document.createElement('style');
    style.textContent =
      '.ur-toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:1000;' +
      'max-width:min(420px,calc(100vw - 32px));padding:12px 16px;border-radius:12px;' +
      'background:var(--panel,#fff);color:#D64545;border:1px solid rgba(214,69,69,.35);' +
      'box-shadow:0 14px 34px -8px rgba(0,0,0,.18);font:600 13.5px/1.5 Inter,sans-serif;text-align:center;}';
    document.head.appendChild(style);
  }

  // Brief error message for actions that have no error slot of their own
  // (e.g. the save heart).
  var toastEl = null;
  var toastTimer = null;
  function toast(message){
    addToastStyle();
    if(!toastEl){
      toastEl = document.createElement('div');
      toastEl.className = 'ur-toast';
      toastEl.setAttribute('role', 'alert');
      document.body.appendChild(toastEl);
    }
    toastEl.textContent = message;
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function(){ toastEl.hidden = true; }, 5000);
  }

  // Reuse a section's empty-state panel to report that its data failed to
  // load, instead of implying there's simply nothing there. The page still
  // decides when the panel is visible.
  function showEmptyStateError(el, title, message){
    if(!el) return;
    var h3 = el.querySelector('h3');
    var p = el.querySelector('p');
    if(!('urOriginal' in el.dataset)){
      el.dataset.urOriginal = JSON.stringify([h3 ? h3.textContent : '', p ? p.textContent : '']);
    }
    if(h3) h3.textContent = title;
    if(p) p.textContent = message;
    el.querySelectorAll('.empty-actions, a.btn-dark').forEach(function(a){ a.hidden = true; });
  }

  function resetEmptyState(el){
    if(!el || !('urOriginal' in el.dataset)) return;
    var original = JSON.parse(el.dataset.urOriginal);
    delete el.dataset.urOriginal;
    var h3 = el.querySelector('h3');
    var p = el.querySelector('p');
    if(h3) h3.textContent = original[0];
    if(p) p.textContent = original[1];
    el.querySelectorAll('.empty-actions, a.btn-dark').forEach(function(a){ a.hidden = false; });
  }

  window.apiFetch = apiFetch;
  window.urAuth = {
    getToken: getToken,
    clearSession: clearSession,
    getMe: getMe,
    firstName: firstName,
    redirectToLogin: redirectToLogin,
    siteBase: siteBase,
  };
  window.urUi = {
    errorMessage: errorMessage,
    apiError: apiError,
    toast: toast,
    showEmptyStateError: showEmptyStateError,
    resetEmptyState: resetEmptyState,
  };
})();

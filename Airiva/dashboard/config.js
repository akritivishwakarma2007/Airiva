/**
 * config.js — Airiva Frontend Configuration & Unified API Base
 * Standardizes all backend requests under the /v1 versioned prefix.
 */
(function() {
  'use strict';

  // Determine local vs production API host
  const isLocal = typeof window !== 'undefined' && (
    window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1' ||
    window.location.protocol === 'file:'
  );

  const defaultBase = isLocal
    ? (window.location.port === '8000' ? 'http://127.0.0.1:8000/v1' : 'http://localhost:8000/v1')
    : 'https://airiva.onrender.com/v1';

  // Allow override via <script data-api-base="..."> or window.AIRIVA_API_BASE
  const scriptTag = typeof document !== 'undefined' ? document.querySelector('script[data-api-base]') : null;
  const configOverride = scriptTag ? scriptTag.getAttribute('data-api-base') : (typeof window !== 'undefined' ? window.AIRIVA_API_BASE : null);

  const API_BASE = (configOverride || defaultBase).replace(/\/+$/, '');

  if (typeof window !== 'undefined') {
    window.API_BASE = API_BASE;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { API_BASE };
  }
})();

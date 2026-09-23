// Deploy-time settings for the frontend. This is the only file to change
// when the API moves.
//
// apiBaseUrl: where the backend lives, with no trailing slash, e.g.
// "https://your-api.up.railway.app". Leave it empty when the backend serves
// these pages itself (local dev: uvicorn on :8000), so requests stay same-origin.
window.UR_CONFIG = {
  apiBaseUrl: '',
};

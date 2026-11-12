// API_URL is set at build time when the API lives on another domain (Render):
//   ng build --configuration production --define "API_URL='https://balancer-api.onrender.com/api/v1'"
// Without it the app calls /api/v1 on its own domain (the Docker/Caddy server setup).
declare const API_URL: string | undefined;

export const environment = {
  production: true,
  apiUrl: typeof API_URL === 'string' && API_URL ? API_URL : '/api/v1',
};

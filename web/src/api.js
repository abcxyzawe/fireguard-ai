import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || '';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
});

export const getStatus = () => api.get('/api/status');
export const getConfig = () => api.get('/api/config');
export const updateConfig = (data) => api.post('/api/config', data);
export const getHistory = (limit = 50, type = 'all') =>
  api.get(`/api/history?limit=${limit}&type=${type}`);

export const detectImage = (file) => {
  const form = new FormData();
  form.append('file', file);
  return api.post('/api/detect_upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  });
};

export const detectVideo = (file) => {
  const form = new FormData();
  form.append('file', file);
  return api.post('/api/detect_video', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  });
};

export const getVideoStatus = (jobId) => api.get(`/api/video_status/${jobId}`);
export const getVideoResultUrl = (jobId) => `${API_BASE}/api/video_result/${jobId}`;

export const saveCapture = (imageDataUrl) =>
  api.post('/api/save_capture', { image: imageDataUrl });

export const getStreamUrl = (camId = 'cam1') => `${API_BASE}/stream/${camId}`;
export const getLatestUrl = (camId = 'cam1') => `${API_BASE}/latest/${camId}`;

export default api;

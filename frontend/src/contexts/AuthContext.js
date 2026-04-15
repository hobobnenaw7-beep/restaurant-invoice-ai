import { createContext, useContext, useState, useEffect, useCallback, useMemo, useRef } from 'react';
import axios from 'axios';

const API_URL = `${process.env.REACT_APP_BACKEND_URL}/api`;
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('ra_token'));
  const [loading, setLoading] = useState(true);

  const apiRef = useRef(null);
  if (!apiRef.current) {
    apiRef.current = axios.create({ baseURL: API_URL });
    apiRef.current.interceptors.request.use((config) => {
      const t = localStorage.getItem('ra_token');
      if (t) config.headers.Authorization = `Bearer ${t}`;
      return config;
    });
  }
  const api = apiRef.current;

  useEffect(() => {
    if (token) {
      api.get('/auth/me')
        .then(res => setUser(res.data))
        .catch(() => { localStorage.removeItem('ra_token'); setToken(null); })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const login = useCallback(async (email, password) => {
    const res = await api.post('/auth/login', { email, password });
    localStorage.setItem('ra_token', res.data.token);
    setToken(res.data.token);
    // Fetch full user data with permissions
    const meRes = await api.get('/auth/me', { headers: { Authorization: `Bearer ${res.data.token}` } });
    setUser(meRes.data);
    return res.data;
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const register = useCallback(async (email, password, name, restaurant_name) => {
    const res = await api.post('/auth/register', { email, password, name, restaurant_name });
    localStorage.setItem('ra_token', res.data.token);
    setToken(res.data.token);
    setUser(res.data.user);
    return res.data;
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const logout = useCallback(() => {
    localStorage.removeItem('ra_token');
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, token, loading, login, register, logout, api }), [user, token, loading, login, register, logout, api]);

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);

import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import api from '../api';

const API_URL = process.env.REACT_APP_BACKEND_URL || '';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [authenticated, setAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);
  const verifyInFlightRef = useRef(null);
  const verifyTimeoutRef = useRef(null);
  const verifiedOnceRef = useRef(false);


  const verifyToken = useCallback(async (token) => {
    if (!token) return false;
    if (verifyInFlightRef.current) {
      return verifyInFlightRef.current;
    }

    verifyInFlightRef.current = (async () => {
      try {
        const res = await fetch(`${API_URL}/api/auth/verify`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
            'X-Access-Token': token,
          },
          body: JSON.stringify({ token }),
        });

        if (res.ok) {
          verifiedOnceRef.current = true;
          setAuthenticated(true);
          return true;
        }

        if (!verifiedOnceRef.current) {
          setAuthenticated(false);
        }
        return false;
      } catch {
        if (!verifiedOnceRef.current) {
          setAuthenticated(false);
        }
        return false;
      } finally {
        verifyInFlightRef.current = null;
        setLoading(false);
      }
    })();

    return verifyInFlightRef.current;
  }, []);

  const scheduleVerify = useCallback((token) => {
    if (verifyTimeoutRef.current) {
      clearTimeout(verifyTimeoutRef.current);
    }
    verifyTimeoutRef.current = setTimeout(() => {
      verifyToken(token);
    }, 150);
  }, [verifyToken]);

  const checkAuth = useCallback(async () => {
    const token = api.getToken();
    if (!token) {
      verifiedOnceRef.current = false;
      setAuthenticated(false);
      setLoading(false);
      return;
    }
    setLoading(true);
    scheduleVerify(token);
  }, [scheduleVerify]);

  useEffect(() => {
    checkAuth();
    const handler = () => {
      verifiedOnceRef.current = false;
      setAuthenticated(false);
      setLoading(false);
    };
    window.addEventListener('sparkbot_unauthorized', handler);
    return () => {
      window.removeEventListener('sparkbot_unauthorized', handler);
      if (verifyTimeoutRef.current) {
        clearTimeout(verifyTimeoutRef.current);
      }
    };
  }, [checkAuth]);

  const login = async (token) => {
    api.setToken(token);
    setLoading(true);
    const ok = await verifyToken(token);
    if (!ok) {
      api.clearToken();
    }
    return ok;
  };

  const logout = () => {
    api.clearToken();
    verifiedOnceRef.current = false;
    setAuthenticated(false);
  };

  return (
    <AuthContext.Provider value={{ authenticated, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

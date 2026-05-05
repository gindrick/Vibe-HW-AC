import { createContext, useContext } from "react";

export const AuthContext = createContext({ user: null });

export function useAuth() {
  return useContext(AuthContext);
}

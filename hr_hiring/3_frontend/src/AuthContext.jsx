import { createContext, useContext } from "react";

export const AuthContext = createContext({ user: null, testMode: false });

export function useAuth() {
  return useContext(AuthContext);
}

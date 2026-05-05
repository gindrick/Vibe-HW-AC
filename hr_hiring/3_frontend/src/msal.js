import { PublicClientApplication } from "@azure/msal-browser";

const clientId = import.meta.env.VITE_ENTRA_CLIENT_ID || "";
const tenantId = import.meta.env.VITE_ENTRA_TENANT_ID || "";
const baseOrigin = window.location.origin;
const redirectPath = import.meta.env.VITE_ENTRA_REDIRECT_PATH || "/hr_hiring/";

export const msalEnabled = Boolean(clientId && tenantId);

const authority = tenantId
  ? `https://login.microsoftonline.com/${tenantId}`
  : "https://login.microsoftonline.com/common";

export const msalInstance = msalEnabled
  ? new PublicClientApplication({
      auth: {
        clientId,
        authority,
        redirectUri: `${baseOrigin}${redirectPath}`,
      },
      cache: {
        cacheLocation: "sessionStorage",
        storeAuthStateInCookie: false,
      },
    })
  : null;

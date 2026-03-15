function unauthenticatedSession() {
  return {
    authenticated: false,
    session: null,
  };
}

export async function GET(request) {
  const session = readSessionFromRequest(request);
  if (!session) {
    return Response.json(unauthenticatedSession(), { status: 200 });
  }

  return Response.json(
    {
      authenticated: true,
      session,
    },
    { status: 200 },
  );
}

function readSessionFromRequest(request) {
  const rawCookieHeader = request?.headers?.get("cookie");
  if (!rawCookieHeader) {
    return null;
  }

  const sessionCookieValue = findSessionCookieValue(rawCookieHeader);
  if (!sessionCookieValue) {
    return null;
  }

  const rawValue = normalizeCookieValue(sessionCookieValue);
  if (!rawValue) {
    return null;
  }

  try {
    const parsed = JSON.parse(decodeURIComponent(rawValue));
    const user = normalizeUser(parsed?.user);
    const expires = typeof parsed?.expires === "string" ? parsed.expires.trim() : "";
    if (!user || !expires) {
      return null;
    }

    return {
      user,
      expires,
    };
  } catch {
    return null;
  }
}

function normalizeCookieValue(value) {
  const trimmedValue = typeof value === "string" ? value.trim() : "";
  if (!trimmedValue) {
    return "";
  }

  const hasWrappingQuotes =
    trimmedValue.startsWith('"') && trimmedValue.endsWith('"') && trimmedValue.length >= 2;
  if (!hasWrappingQuotes) {
    return trimmedValue;
  }

  return trimmedValue.slice(1, -1).trim();
}

function findSessionCookieValue(cookieHeader) {
  const cookieParts = typeof cookieHeader === "string" ? cookieHeader.split(";") : [];
  for (const part of cookieParts) {
    const trimmedPart = part.trim();
    if (!trimmedPart) {
      continue;
    }

    const equalsIndex = trimmedPart.indexOf("=");
    if (equalsIndex === -1) {
      continue;
    }

    const name = trimmedPart.slice(0, equalsIndex).trim().toLowerCase();
    if (name !== "session") {
      continue;
    }

    return trimmedPart.slice(equalsIndex + 1);
  }

  return null;
}

function normalizeUser(user) {
  if (!user || typeof user !== "object") {
    return null;
  }

  const normalized = {};
  if (typeof user.name === "string" && user.name.trim()) {
    normalized.name = user.name.trim();
  }
  if (typeof user.email === "string" && user.email.trim()) {
    normalized.email = user.email.trim();
  }
  if (typeof user.image === "string" && user.image.trim()) {
    normalized.image = user.image.trim();
  }

  return Object.keys(normalized).length > 0 ? normalized : null;
}

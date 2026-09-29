// Container healthcheck target (Dockerfile HEALTHCHECK).
export function GET(): Response {
  return Response.json({ status: "ok" });
}

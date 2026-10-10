import NextAuth from "next-auth";
import MicrosoftEntraID from "next-auth/providers/microsoft-entra-id";
import { PrismaAdapter } from "@auth/prisma-adapter";
import { prisma } from "@/lib/prisma";
import { UserRole } from "@prisma/client";

export const { handlers, auth, signIn, signOut } = NextAuth({
  // Required when running behind a reverse proxy (Azure Front Door / Container Apps).
  // Auth.js v5 rejects requests from untrusted hosts without this.
  trustHost: true,
  useSecureCookies: process.env.NEXTAUTH_URL?.startsWith("https://") ?? false,
  logger: {
    error(error) {
      // Auth.js error subclasses carry a `type` discriminant that isn't on the
      // base Error type; read it through an unknown-narrowed accessor rather
      // than an `any` cast to keep this type-safe.
      const type = (error as { type?: unknown }).type;
      console.error("[auth][error]", error.name, error.message, JSON.stringify({ cause: error.cause, type }))
    },
    warn(code) {
      console.warn("[auth][warn]", code)
    },
  },
  adapter: PrismaAdapter(prisma),
  providers: [
    MicrosoftEntraID({
      clientId: process.env.AZURE_AD_CLIENT_ID!,
      clientSecret: process.env.AZURE_AD_CLIENT_SECRET!,
      // next-auth v5 beta dropped tenantId as a standalone prop.
      // Pass the OIDC issuer URL directly; the provider appends
      // /.well-known/openid-configuration for discovery.
      issuer: `https://login.microsoftonline.com/${process.env.AZURE_AD_TENANT_ID}/v2.0`,
      // Entra ID does not always populate the `email` claim — admin and
      // service accounts often only have `preferred_username` (the UPN).
      // PrismaAdapter requires a non-null email to create the User row, so
      // we fall back to preferred_username (always non-null for org accounts).
      profile(profile) {
        return {
          id: profile.sub,
          name: profile.name ?? profile.preferred_username,
          email: profile.email ?? profile.preferred_username,
          image: null,
          // Default role for new users. Existing users retain their DB role.
          role: UserRole.ANALYST,
        };
      },
    }),
  ],
  callbacks: {
    // Attach user role to the session token so UI can make auth decisions.
    async session({ session, user }) {
      if (session.user && user) {
        session.user.id = user.id;
        session.user.role = user.role;
      }
      return session;
    },
  },
  pages: {
    signIn: "/auth/signin",
    error: "/auth/error",
  },
});

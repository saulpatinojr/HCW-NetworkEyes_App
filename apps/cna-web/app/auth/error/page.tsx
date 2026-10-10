// Auth.js v5 redirects here when authentication fails.
// The `error` query param contains the error code (e.g. "OAuthSignin",
// "OAuthCallback", "OAuthCreateAccount", "Callback", "OAuthAccountNotLinked",
// "EmailCreateAccount", "CredentialsSignin", "SessionRequired").
const AUTH_ERROR_MESSAGES: Record<string, string> = {
  OAuthSignin: "Could not initiate sign-in with Microsoft. Please try again.",
  OAuthCallback: "Microsoft returned an error during sign-in. Please try again.",
  OAuthCreateAccount: "Could not create your account. Contact your administrator.",
  OAuthAccountNotLinked:
    "This Microsoft account is already linked to a different user.",
  Callback: "An error occurred during sign-in callback.",
  SessionRequired: "You must be signed in to access this page.",
  Default: "An authentication error occurred.",
};

export default async function AuthErrorPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const params = await searchParams;
  const error = params.error ?? "Default";
  const message = AUTH_ERROR_MESSAGES[error] ?? AUTH_ERROR_MESSAGES.Default;

  return (
    <div className="flex min-h-screen flex-col items-center justify-center">
      <div className="glass w-full max-w-sm p-8">
        <h1 className="mb-2 text-2xl font-black tracking-tight text-navy-800 dark:text-navy-50">
          Sign-in failed
        </h1>
        <p className="mb-6 text-sm text-navy-400 dark:text-navy-300">{message}</p>
        {process.env.NODE_ENV !== "production" && (
          <p className="mb-4 rounded-lg bg-navy-50 dark:bg-navy-800/50 p-2 font-mono text-xs text-navy-500 dark:text-navy-300">
            error: {error}
          </p>
        )}
        <a href="/auth/signin" className="btn-teal w-full justify-center">
          Try again
        </a>
      </div>
    </div>
  );
}

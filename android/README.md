# Package Tracker Android wrapper

This Trusted Web Activity project wraps the Package Tracker PWA using the package ID
`com.alekhyakusam.packagetracker` and targets Android API 36.

The checked-in configuration currently points to a temporary `trycloudflare.com` URL and must be
updated to a permanent HTTPS domain before a production Google Play release. The local
`android.keystore`, APK, and AAB files are intentionally excluded from Git.

Build with Bubblewrap from this directory:

```sh
bubblewrap build
```

The build creates `app-release-signed.apk` for device testing and `app-release-bundle.aab` for
Google Play. Use a securely backed-up production upload key before publishing.

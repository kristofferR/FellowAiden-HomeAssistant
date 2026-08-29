# Android Surface Model

## App Wrapper
- `MainApplication`: `evidence/code/is/symphony/FellowDev/MainApplication.java` enables React Native new architecture and Hermes.
- `MainActivity`: `evidence/code/is/symphony/FellowDev/MainActivity.java` boots component `Fellow` with a portrait-only `singleTask` activity.
- `BuildConfig`: `evidence/code/is/symphony/FellowDev/BuildConfig.java` exposes `API_GATEWAY_URL`, `LINKING_PREFIXES`, `MIXPANEL_TOKEN`, and production environment flags through `RNCConfigModule`.

## Exported Entry Points
- `activity` `is.symphony.FellowDev.MainActivity` exported=`true`
- `activity` `com.google.android.gms.auth.api.signin.internal.SignInHubActivity` exported=`false`
- `activity` `com.google.android.gms.common.api.GoogleApiActivity` exported=`false`

## Deep-Link Surface
- `fellow://` autoVerify=`false` categories=`android.intent.category.BROWSABLE, android.intent.category.DEFAULT`
- `https://brew.link/p` autoVerify=`true` categories=`android.intent.category.BROWSABLE, android.intent.category.DEFAULT`
- `https://fellow-staging.myshopify.com/account/activate` autoVerify=`true` categories=`android.intent.category.BROWSABLE, android.intent.category.DEFAULT`
- `https://fellowproducts.com/account/activate` autoVerify=`true` categories=`android.intent.category.BROWSABLE, android.intent.category.DEFAULT`

## React Native Package Inventory
- Core Runtime: `MainReactPackage`, `AsyncStoragePackage`, `ClipboardPackage`, `RNBootSplashPackage`, `RNGestureHandlerPackage`, `OrientationPackage`, `ReanimatedPackage`, `SafeAreaContextPackage`, `RNScreensPackage`
- Device Connectivity: `GeolocationPackage`, `NetInfoPackage`, `BleManagerPackage`, `RNDeviceInfo`, `RNFusedLocationPackage`, `RNPermissionsPackage`, `RNWifiPackage`
- Storage Identity: `RNCConfigPackage`, `EmailPackage`, `RNGetRandomValuesPackage`, `KeychainPackage`, `RandomBytesPackage`
- Notifications Analytics: `ReactNativeFirebaseAnalyticsPackage`, `ReactNativeFirebaseAppPackage`, `ReactNativeFirebaseMessagingPackage`, `MixpanelReactNativePackage`
- Ui Media: `BlurViewPackage`, `ReactSliderPackage`, `RNSkiaPackage`, `LottiePackage`, `BlurhashPackage`, `LinearGradientPackage`, `SvgPackage`, `TurboImagePackage`, `ReactVideoPackage`
- Other: `ReactNativeFirebaseCrashlyticsPackage`, `WorkletsPackage`

## Connectivity And Provisioning Seams
- BLE: `BleManagerPackage` plus `NativeBleManagerSpec` exposes scan, connect, read, write, MTU, notification, and companion-device association methods.
- Wi-Fi: `RNWifiPackage` plus `wifiutils` exposes list, connect, disconnect, and current-SSID operations.
- Notifications: Firebase Analytics + Firebase Messaging packages are registered in `PackageList` and backed by manifest services/receivers.
- Storage: `KeychainPackage` and AsyncStorage are bundled alongside `RNCConfigModule` for config injection.

## Security Observations
- No app-package references to `networkSecurityConfig`, `usesCleartextTraffic`, `CertificatePinner`, custom `HostnameVerifier`, `SSLSocketFactory`, or `X509TrustManager` were found in the app-specific wrapper files or decoded manifest.

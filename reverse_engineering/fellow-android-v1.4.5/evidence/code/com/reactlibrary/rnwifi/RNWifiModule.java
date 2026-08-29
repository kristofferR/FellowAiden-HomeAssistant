package com.reactlibrary.rnwifi;

import android.content.Intent;
import android.content.IntentFilter;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.NetworkInfo;
import android.net.NetworkRequest;
import android.net.Uri;
import android.net.wifi.WifiConfiguration;
import android.net.wifi.WifiManager;
import android.net.wifi.WifiNetworkSpecifier;
import android.net.wifi.WifiNetworkSuggestion;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.util.Log;
import androidx.media3.exoplayer.Renderer;
import com.facebook.react.bridge.Promise;
import com.facebook.react.bridge.ReactApplicationContext;
import com.facebook.react.bridge.ReactContextBaseJavaModule;
import com.facebook.react.bridge.ReactMethod;
import com.facebook.react.bridge.ReadableArray;
import com.facebook.react.bridge.ReadableMap;
import com.reactlibrary.rnwifi.errors.ConnectErrorCodes;
import com.reactlibrary.rnwifi.errors.DisconnectErrorCodes;
import com.reactlibrary.rnwifi.errors.ForceWifiUsageErrorCodes;
import com.reactlibrary.rnwifi.errors.GetCurrentWifiSSIDErrorCodes;
import com.reactlibrary.rnwifi.errors.IsEnabledErrorCodes;
import com.reactlibrary.rnwifi.errors.IsRemoveWifiNetworkErrorCodes;
import com.reactlibrary.rnwifi.errors.LoadWifiListErrorCodes;
import com.reactlibrary.rnwifi.mappers.WifiScanResultsMapper;
import com.reactlibrary.rnwifi.receivers.WifiScanResultReceiver;
import com.reactlibrary.rnwifi.utils.LocationUtils;
import com.reactlibrary.rnwifi.utils.PermissionUtils;
import com.thanosfisherman.wifiutils.WifiUtils;
import com.thanosfisherman.wifiutils.wifiConnect.DisconnectCallbackHolder;
import com.thanosfisherman.wifiutils.wifiDisconnect.DisconnectionErrorCode;
import com.thanosfisherman.wifiutils.wifiDisconnect.DisconnectionSuccessListener;
import com.thanosfisherman.wifiutils.wifiRemove.RemoveErrorCode;
import com.thanosfisherman.wifiutils.wifiRemove.RemoveSuccessListener;
import java.util.ArrayList;

/* JADX INFO: loaded from: classes3.dex */
public class RNWifiModule extends ReactContextBaseJavaModule {
    static final /* synthetic */ boolean $assertionsDisabled = false;
    private static String TAG = "RNWifiModule";
    private static final int TIMEOUT_MILLIS = 15000;
    private static final int TIMEOUT_REMOVE_MILLIS = 10000;
    private final ReactApplicationContext context;
    private Network joinedNetwork;
    private final WifiManager wifi;

    RNWifiModule(ReactApplicationContext reactApplicationContext) {
        super(reactApplicationContext);
        this.wifi = (WifiManager) reactApplicationContext.getApplicationContext().getSystemService("wifi");
        this.context = reactApplicationContext;
    }

    @Override // com.facebook.react.bridge.NativeModule
    public String getName() {
        return "WifiManager";
    }

    @ReactMethod
    public void loadWifiList(Promise promise) {
        if (assertLocationPermissionGranted(promise)) {
            try {
                promise.resolve(WifiScanResultsMapper.mapWifiScanResults(this.wifi.getScanResults()));
            } catch (Exception e) {
                promise.reject(LoadWifiListErrorCodes.exception.toString(), e.getMessage());
            }
        }
    }

    @ReactMethod
    @Deprecated
    public void forceWifiUsage(boolean z, Promise promise) {
        forceWifiUsageWithOptions(z, null, promise);
    }

    @ReactMethod
    public void forceWifiUsageWithOptions(boolean z, ReadableMap readableMap, final Promise promise) {
        if (z) {
            try {
                boolean zCanWrite = Settings.System.canWrite(this.context);
                int iCheckCallingOrSelfPermission = this.context.checkCallingOrSelfPermission("android.permission.CHANGE_NETWORK_STATE");
                if (!zCanWrite && iCheckCallingOrSelfPermission != 0) {
                    Intent intent = new Intent("android.settings.action.MANAGE_WRITE_SETTINGS");
                    intent.setData(Uri.parse("package:" + this.context.getPackageName()));
                    intent.addFlags(268435456);
                    this.context.startActivity(intent);
                }
            } catch (Exception e) {
                promise.reject("", e.getMessage());
                return;
            }
        }
        final ConnectivityManager connectivityManager = (ConnectivityManager) this.context.getSystemService("connectivity");
        if (connectivityManager == null) {
            promise.reject(ForceWifiUsageErrorCodes.couldNotGetConnectivityManager.toString(), "Failed to get the ConnectivityManager.");
            return;
        }
        if (z) {
            Network network = this.joinedNetwork;
            if (network != null) {
                selectNetwork(network, connectivityManager);
                promise.resolve(null);
                return;
            }
            NetworkRequest.Builder builderAddTransportType = new NetworkRequest.Builder().addTransportType(1);
            if (readableMap != null && readableMap.getBoolean("noInternet")) {
                builderAddTransportType.removeCapability(12);
            }
            connectivityManager.requestNetwork(builderAddTransportType.build(), new ConnectivityManager.NetworkCallback() { // from class: com.reactlibrary.rnwifi.RNWifiModule.1
                @Override // android.net.ConnectivityManager.NetworkCallback
                public void onAvailable(Network network2) {
                    super.onAvailable(network2);
                    RNWifiModule.this.selectNetwork(network2, connectivityManager);
                    connectivityManager.unregisterNetworkCallback(this);
                    promise.resolve(null);
                }
            });
            return;
        }
        connectivityManager.bindProcessToNetwork(null);
        promise.resolve(null);
    }

    @ReactMethod
    public void isEnabled(Promise promise) {
        WifiManager wifiManager = this.wifi;
        if (wifiManager == null) {
            promise.reject(IsEnabledErrorCodes.couldNotGetWifiManager.toString(), "Failed to initialize the WifiManager.");
        } else {
            promise.resolve(Boolean.valueOf(wifiManager.isWifiEnabled()));
        }
    }

    @ReactMethod
    public void setEnabled(boolean z) {
        if (isAndroidTenOrLater()) {
            openWifiSettings();
        } else {
            this.wifi.setWifiEnabled(z);
        }
    }

    @ReactMethod
    public void openWifiSettings() {
        Intent intent = new Intent("android.settings.panel.action.WIFI");
        intent.addFlags(268435456);
        this.context.startActivity(intent);
    }

    @ReactMethod
    public void connectToProtectedSSID(final String str, final String str2, boolean z, final boolean z2, final Promise promise) {
        if (assertLocationPermissionGranted(promise)) {
            if (!this.wifi.isWifiEnabled() && !this.wifi.setWifiEnabled(true)) {
                promise.reject(ConnectErrorCodes.couldNotEnableWifi.toString(), "On Android 10, the user has to enable wifi manually.");
            } else {
                removeWifiNetwork(str, promise, new Runnable() { // from class: com.reactlibrary.rnwifi.RNWifiModule$$ExternalSyntheticLambda4
                    @Override // java.lang.Runnable
                    public final void run() {
                        this.f$0.lambda$connectToProtectedSSID$0(str, str2, z2, promise);
                    }
                }, 10000);
            }
        }
    }

    /* JADX INFO: Access modifiers changed from: private */
    public /* synthetic */ void lambda$connectToProtectedSSID$0(String str, String str2, boolean z, Promise promise) {
        lambda$connectToProtectedWifiSSID$1(str, str2, z, TIMEOUT_MILLIS, promise);
    }

    @ReactMethod
    public void connectToProtectedWifiSSID(ReadableMap readableMap, final Promise promise) {
        if (assertLocationPermissionGranted(promise)) {
            if (!this.wifi.isWifiEnabled() && !this.wifi.setWifiEnabled(true)) {
                promise.reject(ConnectErrorCodes.couldNotEnableWifi.toString(), "On Android 10, the user has to enable wifi manually.");
                return;
            }
            final String string = readableMap.getString("ssid");
            final String string2 = readableMap.getString("password");
            final boolean z = readableMap.hasKey("isHidden") && readableMap.getBoolean("isHidden");
            final int i = readableMap.hasKey("timeout") ? readableMap.getInt("timeout") * 1000 : TIMEOUT_MILLIS;
            removeWifiNetwork(string, promise, new Runnable() { // from class: com.reactlibrary.rnwifi.RNWifiModule$$ExternalSyntheticLambda0
                @Override // java.lang.Runnable
                public final void run() {
                    this.f$0.lambda$connectToProtectedWifiSSID$1(string, string2, z, i, promise);
                }
            }, 10000);
        }
    }

    @ReactMethod
    public void suggestWifiNetwork(ReadableArray readableArray, Promise promise) {
        if (assertLocationPermissionGranted(promise)) {
            ArrayList arrayList = new ArrayList();
            for (int i = 0; i < readableArray.size(); i++) {
                ReadableMap map = readableArray.getMap(i);
                if (map != null) {
                    String string = map.getString("ssid");
                    String string2 = map.hasKey("password") ? map.getString("password") : "";
                    boolean z = map.hasKey("isWpa3") && map.getBoolean("isWpa3");
                    boolean z2 = map.hasKey("isAppInteractionRequired") && map.getBoolean("isAppInteractionRequired");
                    WifiNetworkSuggestion.Builder ssid = new WifiNetworkSuggestion.Builder().setSsid(string);
                    if (z2) {
                        ssid.setIsAppInteractionRequired(true);
                    }
                    if (z) {
                        ssid.setWpa3Passphrase(string2);
                    } else if (!string2.isEmpty()) {
                        ssid.setWpa2Passphrase(string2);
                    }
                    arrayList.add(ssid.build());
                }
            }
            int iAddNetworkSuggestions = ((WifiManager) getReactApplicationContext().getSystemService("wifi")).addNetworkSuggestions(arrayList);
            if (iAddNetworkSuggestions == 0) {
                promise.resolve("suggestions_added");
                return;
            }
            if (iAddNetworkSuggestions == 1) {
                promise.reject(ConnectErrorCodes.unableToConnect.toString(), "Internal error occurred while adding network suggestions.");
                return;
            }
            if (iAddNetworkSuggestions == 2) {
                promise.reject(ConnectErrorCodes.unableToConnect.toString(), "App is not allowed to add network suggestions.");
                return;
            }
            if (iAddNetworkSuggestions == 3) {
                promise.resolve("suggestions_already_added");
            } else if (iAddNetworkSuggestions == 4) {
                promise.reject(ConnectErrorCodes.unableToConnect.toString(), "Maximum number of network suggestions exceeded for this app.");
            } else {
                promise.reject(ConnectErrorCodes.unableToConnect.toString(), "Failed to add network suggestions. Status: " + iAddNetworkSuggestions);
            }
        }
    }

    private boolean getConnectionStatus() {
        Network network;
        ConnectivityManager connectivityManager = (ConnectivityManager) getReactApplicationContext().getSystemService("connectivity");
        if (connectivityManager == null) {
            return false;
        }
        if (isAndroidTenOrLater() && (network = this.joinedNetwork) != null) {
            NetworkCapabilities networkCapabilities = connectivityManager.getNetworkCapabilities(network);
            return (networkCapabilities != null && networkCapabilities.hasTransport(1)) && (networkCapabilities != null && networkCapabilities.hasCapability(21) && networkCapabilities.hasCapability(13));
        }
        NetworkInfo networkInfo = connectivityManager.getNetworkInfo(1);
        if (networkInfo == null) {
            return false;
        }
        return networkInfo.isConnected();
    }

    @ReactMethod
    public void connectionStatus(Promise promise) {
        promise.resolve(Boolean.valueOf(getConnectionStatus()));
    }

    @ReactMethod
    public void disconnect(final Promise promise) {
        final Handler handler = new Handler(Looper.getMainLooper());
        final Runnable runnable = new Runnable() { // from class: com.reactlibrary.rnwifi.RNWifiModule$$ExternalSyntheticLambda3
            @Override // java.lang.Runnable
            public final void run() {
                this.f$0.lambda$disconnect$2(promise);
            }
        };
        handler.postDelayed(runnable, Renderer.DEFAULT_DURATION_TO_PROGRESS_US);
        WifiUtils.withContext(this.context).disconnect(new DisconnectionSuccessListener() { // from class: com.reactlibrary.rnwifi.RNWifiModule.2
            @Override // com.thanosfisherman.wifiutils.wifiDisconnect.DisconnectionSuccessListener
            public void success() {
                handler.removeCallbacks(runnable);
                promise.resolve(true);
            }

            @Override // com.thanosfisherman.wifiutils.wifiDisconnect.DisconnectionSuccessListener
            public void failed(DisconnectionErrorCode disconnectionErrorCode) {
                handler.removeCallbacks(runnable);
                int i = AnonymousClass5.$SwitchMap$com$thanosfisherman$wifiutils$wifiDisconnect$DisconnectionErrorCode[disconnectionErrorCode.ordinal()];
                if (i == 1) {
                    promise.reject(DisconnectErrorCodes.couldNotGetWifiManager.toString(), "Could not get WifiManager.");
                } else {
                    if (i == 2) {
                    }
                    promise.resolve(false);
                }
                promise.reject(DisconnectErrorCodes.couldNotGetConnectivityManager.toString(), "Could not get Connectivity Manager.");
                promise.resolve(false);
            }
        });
    }

    /* JADX INFO: Access modifiers changed from: private */
    public /* synthetic */ void lambda$disconnect$2(Promise promise) {
        promise.reject(ConnectErrorCodes.timeoutOccurred.toString(), "Connection timeout");
        if (isAndroidTenOrLater()) {
            DisconnectCallbackHolder.getInstance().unbindProcessFromNetwork();
            DisconnectCallbackHolder.getInstance().disconnect();
        }
    }

    @ReactMethod
    public void getCurrentWifiSSID(Promise promise) {
        if (assertLocationPermissionGranted(promise)) {
            String wifiSSID = getWifiSSID();
            if (wifiSSID == null) {
                promise.reject(GetCurrentWifiSSIDErrorCodes.couldNotDetectSSID.toString(), "Not connected or connecting.");
            } else {
                promise.resolve(wifiSSID);
            }
        }
    }

    @ReactMethod
    public void getBSSID(Promise promise) {
        promise.resolve(this.wifi.getConnectionInfo().getBSSID().toUpperCase());
    }

    @ReactMethod
    public void getCurrentSignalStrength(Promise promise) {
        promise.resolve(Integer.valueOf(this.wifi.getConnectionInfo().getRssi()));
    }

    @ReactMethod
    public void getFrequency(Promise promise) {
        promise.resolve(Integer.valueOf(this.wifi.getConnectionInfo().getFrequency()));
    }

    @ReactMethod
    public void getIP(Promise promise) {
        promise.resolve(longToIP(this.wifi.getConnectionInfo().getIpAddress()));
    }

    @ReactMethod
    public void isRemoveWifiNetwork(String str, Promise promise) {
        removeWifiNetwork(str, promise, null, 10000);
    }

    private void removeWifiNetwork(String str, final Promise promise, final Runnable runnable, int i) {
        if (!PermissionUtils.isLocationPermissionGranted(this.context)) {
            promise.reject(IsRemoveWifiNetworkErrorCodes.locationPermissionMissing.toString(), "Location permission (ACCESS_FINE_LOCATION) is not granted");
            return;
        }
        final Handler handler = new Handler(Looper.getMainLooper());
        final Runnable runnable2 = new Runnable() { // from class: com.reactlibrary.rnwifi.RNWifiModule$$ExternalSyntheticLambda1
            @Override // java.lang.Runnable
            public final void run() {
                this.f$0.lambda$removeWifiNetwork$3(promise);
            }
        };
        handler.postDelayed(runnable2, i);
        WifiUtils.withContext(this.context).remove(str, new RemoveSuccessListener() { // from class: com.reactlibrary.rnwifi.RNWifiModule.3
            @Override // com.thanosfisherman.wifiutils.wifiRemove.RemoveSuccessListener
            public void success() {
                handler.removeCallbacks(runnable2);
                RNWifiModule.this.joinedNetwork = null;
                Runnable runnable3 = runnable;
                if (runnable3 != null) {
                    runnable3.run();
                } else {
                    promise.resolve(true);
                }
            }

            /* JADX WARN: Code duplicated, block: B:11:0x0034  */
            /* JADX WARN: Code duplicated, block: B:13:0x0038  */
            @Override // com.thanosfisherman.wifiutils.wifiRemove.RemoveSuccessListener
            public void failed(RemoveErrorCode removeErrorCode) {
                Runnable runnable3;
                handler.removeCallbacks(runnable2);
                int i2 = AnonymousClass5.$SwitchMap$com$thanosfisherman$wifiutils$wifiRemove$RemoveErrorCode[removeErrorCode.ordinal()];
                if (i2 == 1) {
                    promise.reject(IsRemoveWifiNetworkErrorCodes.couldNotGetWifiManager.toString(), "Could not get WifiManager.");
                } else {
                    if (i2 == 2) {
                    }
                    runnable3 = runnable;
                    if (runnable3 != null) {
                        runnable3.run();
                    } else {
                        promise.resolve(false);
                    }
                }
                promise.reject(IsRemoveWifiNetworkErrorCodes.couldNotGetConnectivityManager.toString(), "Could not get Connectivity Manager.");
                runnable3 = runnable;
                if (runnable3 != null) {
                    runnable3.run();
                } else {
                    promise.resolve(false);
                }
            }
        });
    }

    /* JADX INFO: Access modifiers changed from: private */
    public /* synthetic */ void lambda$removeWifiNetwork$3(Promise promise) {
        promise.reject(ConnectErrorCodes.timeoutOccurred.toString(), "Connection timeout");
        if (isAndroidTenOrLater()) {
            DisconnectCallbackHolder.getInstance().unbindProcessFromNetwork();
            DisconnectCallbackHolder.getInstance().disconnect();
        }
    }

    /* JADX INFO: renamed from: com.reactlibrary.rnwifi.RNWifiModule$5, reason: invalid class name */
    static /* synthetic */ class AnonymousClass5 {
        static final /* synthetic */ int[] $SwitchMap$com$thanosfisherman$wifiutils$wifiDisconnect$DisconnectionErrorCode;
        static final /* synthetic */ int[] $SwitchMap$com$thanosfisherman$wifiutils$wifiRemove$RemoveErrorCode;

        static {
            int[] iArr = new int[RemoveErrorCode.values().length];
            $SwitchMap$com$thanosfisherman$wifiutils$wifiRemove$RemoveErrorCode = iArr;
            try {
                iArr[RemoveErrorCode.COULD_NOT_GET_WIFI_MANAGER.ordinal()] = 1;
            } catch (NoSuchFieldError unused) {
            }
            try {
                $SwitchMap$com$thanosfisherman$wifiutils$wifiRemove$RemoveErrorCode[RemoveErrorCode.COULD_NOT_GET_CONNECTIVITY_MANAGER.ordinal()] = 2;
            } catch (NoSuchFieldError unused2) {
            }
            try {
                $SwitchMap$com$thanosfisherman$wifiutils$wifiRemove$RemoveErrorCode[RemoveErrorCode.COULD_NOT_REMOVE.ordinal()] = 3;
            } catch (NoSuchFieldError unused3) {
            }
            int[] iArr2 = new int[DisconnectionErrorCode.values().length];
            $SwitchMap$com$thanosfisherman$wifiutils$wifiDisconnect$DisconnectionErrorCode = iArr2;
            try {
                iArr2[DisconnectionErrorCode.COULD_NOT_GET_WIFI_MANAGER.ordinal()] = 1;
            } catch (NoSuchFieldError unused4) {
            }
            try {
                $SwitchMap$com$thanosfisherman$wifiutils$wifiDisconnect$DisconnectionErrorCode[DisconnectionErrorCode.COULD_NOT_GET_CONNECTIVITY_MANAGER.ordinal()] = 2;
            } catch (NoSuchFieldError unused5) {
            }
            try {
                $SwitchMap$com$thanosfisherman$wifiutils$wifiDisconnect$DisconnectionErrorCode[DisconnectionErrorCode.COULD_NOT_DISCONNECT.ordinal()] = 3;
            } catch (NoSuchFieldError unused6) {
            }
        }
    }

    @ReactMethod
    public void reScanAndLoadWifiList(Promise promise) {
        if (assertLocationPermissionGranted(promise)) {
            boolean zStartScan = this.wifi.startScan();
            Log.d(TAG, "wifi start scan: " + zStartScan);
            if (zStartScan) {
                getReactApplicationContext().registerReceiver(new WifiScanResultReceiver(this.wifi, promise), new IntentFilter("android.net.wifi.SCAN_RESULTS"));
            } else {
                Log.d(TAG, "Wifi scan rejected");
                promise.resolve("Starting Android 9, it's only allowed to scan 4 times per 2 minuts in a foreground app.");
            }
        }
    }

    /* JADX INFO: Access modifiers changed from: private */
    /* JADX INFO: renamed from: connectToWifiDirectly, reason: merged with bridge method [inline-methods] */
    public void lambda$connectToProtectedWifiSSID$1(String str, String str2, boolean z, int i, Promise promise) {
        if (isAndroidTenOrLater()) {
            connectAndroidQ(str, str2, z, i, promise);
        } else {
            connectPreAndroidQ(str, str2, promise);
        }
    }

    private void connectPreAndroidQ(String str, String str2, Promise promise) {
        WifiConfiguration wifiConfiguration = new WifiConfiguration();
        wifiConfiguration.SSID = formatWithBackslashes(str);
        if (!isNullOrEmpty(str2)) {
            stuffWifiConfigurationWithWPA2(wifiConfiguration, str2);
        } else {
            stuffWifiConfigurationWithoutEncryption(wifiConfiguration);
        }
        int iAddNetwork = this.wifi.addNetwork(wifiConfiguration);
        if (iAddNetwork == -1) {
            promise.reject(ConnectErrorCodes.unableToConnect.toString(), String.format("Could not add or update network configuration with SSID %s", str));
            return;
        }
        if (!this.wifi.enableNetwork(iAddNetwork, true)) {
            promise.reject(ConnectErrorCodes.unableToConnect.toString(), String.format("Failed to enable network with %s", str));
            return;
        }
        if (!this.wifi.reconnect()) {
            promise.reject(ConnectErrorCodes.unableToConnect.toString(), String.format("Failed to reconnect with %s", str));
        } else if (!pollForValidSSID(10, str)) {
            promise.reject(ConnectErrorCodes.unableToConnect.toString(), String.format("Failed to connect with %s", str));
        } else {
            promise.resolve("connected");
        }
    }

    /* JADX INFO: Access modifiers changed from: private */
    public boolean selectNetwork(Network network, ConnectivityManager connectivityManager) {
        return connectivityManager.bindProcessToNetwork(network);
    }

    private void connectAndroidQ(final String str, String str2, boolean z, int i, final Promise promise) {
        WifiNetworkSpecifier.Builder ssid = new WifiNetworkSpecifier.Builder().setIsHiddenSsid(z).setSsid(str);
        if (!isNullOrEmpty(str2)) {
            ssid.setWpa2Passphrase(str2);
        }
        NetworkRequest networkRequestBuild = new NetworkRequest.Builder().addTransportType(1).removeCapability(12).addCapability(13).setNetworkSpecifier(ssid.build()).build();
        DisconnectCallbackHolder.getInstance().disconnect();
        this.joinedNetwork = null;
        ConnectivityManager connectivityManager = (ConnectivityManager) this.context.getSystemService("connectivity");
        final Handler handler = new Handler(Looper.getMainLooper());
        final Runnable runnable = new Runnable() { // from class: com.reactlibrary.rnwifi.RNWifiModule$$ExternalSyntheticLambda2
            @Override // java.lang.Runnable
            public final void run() {
                RNWifiModule.lambda$connectAndroidQ$4(promise);
            }
        };
        handler.postDelayed(runnable, i);
        DisconnectCallbackHolder.getInstance().addNetworkCallback(new ConnectivityManager.NetworkCallback() { // from class: com.reactlibrary.rnwifi.RNWifiModule.4
            @Override // android.net.ConnectivityManager.NetworkCallback
            public void onAvailable(Network network) {
                super.onAvailable(network);
                handler.removeCallbacks(runnable);
                RNWifiModule.this.joinedNetwork = network;
                DisconnectCallbackHolder.getInstance().bindProcessToNetwork(network);
                if (!RNWifiModule.this.pollForValidSSID(3, str)) {
                    promise.reject(ConnectErrorCodes.android10ImmediatelyDroppedConnection.toString(), "Firmware bugs on OnePlus prevent it from connecting on some firmware versions.");
                } else {
                    promise.resolve("connected");
                }
            }

            @Override // android.net.ConnectivityManager.NetworkCallback
            public void onUnavailable() {
                super.onUnavailable();
                handler.removeCallbacks(runnable);
                RNWifiModule.this.joinedNetwork = null;
                promise.reject(ConnectErrorCodes.didNotFindNetwork.toString(), "Network not found or network request cannot be fulfilled.");
            }

            @Override // android.net.ConnectivityManager.NetworkCallback
            public void onLost(Network network) {
                super.onLost(network);
                handler.removeCallbacks(runnable);
                RNWifiModule.this.joinedNetwork = null;
                DisconnectCallbackHolder.getInstance().unbindProcessFromNetwork();
                DisconnectCallbackHolder.getInstance().disconnect();
            }
        }, connectivityManager);
        DisconnectCallbackHolder.getInstance().requestNetwork(networkRequestBuild);
    }

    static /* synthetic */ void lambda$connectAndroidQ$4(Promise promise) {
        promise.reject(ConnectErrorCodes.timeoutOccurred.toString(), "Connection timeout");
        DisconnectCallbackHolder.getInstance().unbindProcessFromNetwork();
        DisconnectCallbackHolder.getInstance().disconnect();
    }

    private static String longToIP(int i) {
        StringBuilder sb = new StringBuilder();
        String[] strArr = {strValueOf, String.valueOf((65535 & i) >>> 8), String.valueOf((16777215 & i) >>> 16), String.valueOf(i >>> 24)};
        String strValueOf = String.valueOf(i & 255);
        sb.append(strValueOf);
        sb.append(".");
        sb.append(strArr[1]);
        sb.append(".");
        sb.append(strArr[2]);
        sb.append(".");
        sb.append(strArr[3]);
        return sb.toString();
    }

    /* JADX INFO: Access modifiers changed from: private */
    public boolean pollForValidSSID(int i, String str) {
        for (int i2 = 0; i2 < i; i2++) {
            try {
                String wifiSSID = getWifiSSID();
                boolean connectionStatus = getConnectionStatus();
                if (wifiSSID != null && wifiSSID.equalsIgnoreCase(str) && connectionStatus) {
                    return true;
                }
                Thread.sleep(1000L);
            } catch (InterruptedException unused) {
            }
        }
        return false;
    }

    private String getWifiSSID() {
        String ssid = this.wifi.getConnectionInfo().getSSID();
        if (ssid.startsWith("\"") && ssid.endsWith("\"")) {
            ssid = ssid.substring(1, ssid.length() - 1);
        }
        if (ssid.equals("<unknown ssid>")) {
            return null;
        }
        return ssid;
    }

    private boolean isAndroidTenOrLater() {
        return Build.VERSION.SDK_INT >= 29;
    }

    private boolean isNullOrEmpty(String str) {
        return str == null || str.trim().isEmpty();
    }

    private void stuffWifiConfigurationWithWPA2(WifiConfiguration wifiConfiguration, String str) {
        if (str.matches("[0-9A-Fa-f]{64}")) {
            wifiConfiguration.preSharedKey = str;
        } else {
            wifiConfiguration.preSharedKey = formatWithBackslashes(str);
        }
        wifiConfiguration.allowedProtocols.set(1);
        wifiConfiguration.allowedProtocols.set(0);
        wifiConfiguration.allowedKeyManagement.set(1);
        wifiConfiguration.status = 2;
        wifiConfiguration.allowedGroupCiphers.set(2);
        wifiConfiguration.allowedGroupCiphers.set(3);
        wifiConfiguration.allowedPairwiseCiphers.set(1);
        wifiConfiguration.allowedPairwiseCiphers.set(2);
    }

    private void stuffWifiConfigurationWithoutEncryption(WifiConfiguration wifiConfiguration) {
        wifiConfiguration.allowedKeyManagement.set(0);
    }

    private String formatWithBackslashes(String str) {
        return String.format("\"%s\"", str);
    }

    private boolean assertLocationPermissionGranted(Promise promise) {
        if (!PermissionUtils.isLocationPermissionGranted(this.context)) {
            promise.reject(ConnectErrorCodes.locationPermissionMissing.toString(), "Location permission (ACCESS_FINE_LOCATION) is not granted");
            return false;
        }
        if (LocationUtils.isLocationOn(this.context)) {
            return true;
        }
        promise.reject(ConnectErrorCodes.locationServicesOff.toString(), "Location service is turned off");
        return false;
    }
}

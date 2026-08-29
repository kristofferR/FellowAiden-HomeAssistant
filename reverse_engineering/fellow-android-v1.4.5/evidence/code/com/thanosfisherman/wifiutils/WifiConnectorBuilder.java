package com.thanosfisherman.wifiutils;

import com.thanosfisherman.wifiutils.wifiConnect.ConnectionScanResultsListener;
import com.thanosfisherman.wifiutils.wifiConnect.ConnectionSuccessListener;
import com.thanosfisherman.wifiutils.wifiDisconnect.DisconnectionSuccessListener;
import com.thanosfisherman.wifiutils.wifiRemove.RemoveSuccessListener;
import com.thanosfisherman.wifiutils.wifiScan.ScanResultsListener;
import com.thanosfisherman.wifiutils.wifiState.WifiStateListener;
import com.thanosfisherman.wifiutils.wifiWps.ConnectionWpsListener;

/* JADX INFO: loaded from: classes3.dex */
public interface WifiConnectorBuilder {

    public interface WifiSuccessListener {
        WifiConnectorBuilder onConnectionResult(ConnectionSuccessListener connectionSuccessListener);

        WifiSuccessListener setTimeout(long j);
    }

    public interface WifiUtilsBuilder {
        void cancelAutoConnect();

        WifiSuccessListener connectWith(String str);

        WifiSuccessListener connectWith(String str, String str2);

        WifiSuccessListener connectWith(String str, String str2, TypeEnum typeEnum);

        WifiSuccessListener connectWith(String str, String str2, String str3);

        WifiSuccessListener connectWithScanResult(String str, ConnectionScanResultsListener connectionScanResultsListener);

        WifiWpsSuccessListener connectWithWps(String str, String str2);

        void disableWifi();

        void disconnect(DisconnectionSuccessListener disconnectionSuccessListener);

        @Deprecated
        void disconnectFrom(String str, DisconnectionSuccessListener disconnectionSuccessListener);

        void enableWifi();

        void enableWifi(WifiStateListener wifiStateListener);

        boolean isWifiConnected();

        boolean isWifiConnected(String str);

        WifiUtilsBuilder patternMatch();

        void remove(String str, RemoveSuccessListener removeSuccessListener);

        WifiConnectorBuilder scanWifi(ScanResultsListener scanResultsListener);
    }

    public interface WifiWpsSuccessListener {
        WifiConnectorBuilder onConnectionWpsResult(ConnectionWpsListener connectionWpsListener);

        WifiWpsSuccessListener setWpsTimeout(long j);
    }

    void start();
}

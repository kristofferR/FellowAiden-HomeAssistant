package com.facebook.react;

import agency.flexible.react.modules.email.EmailPackage;
import android.app.Application;
import android.content.Context;
import android.content.res.Resources;
import com.BV.LinearGradient.LinearGradientPackage;
import com.agontuk.RNFusedLocation.RNFusedLocationPackage;
import com.airbnb.android.react.lottie.LottiePackage;
import com.bitgo.randombytes.RandomBytesPackage;
import com.brentvatne.react.ReactVideoPackage;
import com.facebook.react.shell.MainPackageConfig;
import com.facebook.react.shell.MainReactPackage;
import com.horcrux.svg.SvgPackage;
import com.learnium.RNDeviceInfo.RNDeviceInfo;
import com.lugg.RNCConfig.RNCConfigPackage;
import com.mixpanel.reactnative.MixpanelReactNativePackage;
import com.mrousavy.blurhash.BlurhashPackage;
import com.oblador.keychain.KeychainPackage;
import com.reactlibrary.rnwifi.RNWifiPackage;
import com.reactnativecommunity.asyncstorage.AsyncStoragePackage;
import com.reactnativecommunity.blurview.BlurViewPackage;
import com.reactnativecommunity.clipboard.ClipboardPackage;
import com.reactnativecommunity.geolocation.GeolocationPackage;
import com.reactnativecommunity.netinfo.NetInfoPackage;
import com.reactnativecommunity.slider.ReactSliderPackage;
import com.shopify.reactnative.skia.RNSkiaPackage;
import com.swmansion.gesturehandler.RNGestureHandlerPackage;
import com.swmansion.reanimated.ReanimatedPackage;
import com.swmansion.rnscreens.RNScreensPackage;
import com.swmansion.worklets.WorkletsPackage;
import com.th3rdwave.safeareacontext.SafeAreaContextPackage;
import com.turboimage.TurboImagePackage;
import com.zoontek.rnbootsplash.RNBootSplashPackage;
import com.zoontek.rnpermissions.RNPermissionsPackage;
import io.invertase.firebase.analytics.ReactNativeFirebaseAnalyticsPackage;
import io.invertase.firebase.app.ReactNativeFirebaseAppPackage;
import io.invertase.firebase.crashlytics.ReactNativeFirebaseCrashlyticsPackage;
import io.invertase.firebase.messaging.ReactNativeFirebaseMessagingPackage;
import it.innove.BleManagerPackage;
import java.util.ArrayList;
import java.util.Arrays;
import org.linusu.RNGetRandomValuesPackage;
import org.wonday.orientation.OrientationPackage;

/* JADX INFO: loaded from: classes2.dex */
public class PackageList {
    private Application application;
    private MainPackageConfig mConfig;
    private ReactNativeHost reactNativeHost;

    public PackageList(ReactNativeHost reactNativeHost) {
        this(reactNativeHost, (MainPackageConfig) null);
    }

    public PackageList(Application application) {
        this(application, (MainPackageConfig) null);
    }

    public PackageList(ReactNativeHost reactNativeHost, MainPackageConfig mainPackageConfig) {
        this.reactNativeHost = reactNativeHost;
        this.mConfig = mainPackageConfig;
    }

    public PackageList(Application application, MainPackageConfig mainPackageConfig) {
        this.reactNativeHost = null;
        this.application = application;
        this.mConfig = mainPackageConfig;
    }

    private ReactNativeHost getReactNativeHost() {
        return this.reactNativeHost;
    }

    private Resources getResources() {
        return getApplication().getResources();
    }

    private Application getApplication() {
        ReactNativeHost reactNativeHost = this.reactNativeHost;
        return reactNativeHost == null ? this.application : reactNativeHost.getApplication();
    }

    private Context getApplicationContext() {
        return getApplication().getApplicationContext();
    }

    public ArrayList<ReactPackage> getPackages() {
        return new ArrayList<>(Arrays.asList(new MainReactPackage(this.mConfig), new AsyncStoragePackage(), new ClipboardPackage(), new BlurViewPackage(), new GeolocationPackage(), new NetInfoPackage(), new ReactSliderPackage(), new ReactNativeFirebaseAnalyticsPackage(), new ReactNativeFirebaseAppPackage(), new ReactNativeFirebaseCrashlyticsPackage(), new ReactNativeFirebaseMessagingPackage(), new RNSkiaPackage(), new LottiePackage(), new MixpanelReactNativePackage(), new BleManagerPackage(), new BlurhashPackage(), new RNBootSplashPackage(), new RNCConfigPackage(), new RNDeviceInfo(), new EmailPackage(), new RNFusedLocationPackage(), new RNGestureHandlerPackage(), new RNGetRandomValuesPackage(), new KeychainPackage(), new LinearGradientPackage(), new OrientationPackage(), new RNPermissionsPackage(), new RandomBytesPackage(), new ReanimatedPackage(), new SafeAreaContextPackage(), new RNScreensPackage(), new SvgPackage(), new TurboImagePackage(), new ReactVideoPackage(), new RNWifiPackage(), new WorkletsPackage()));
    }
}

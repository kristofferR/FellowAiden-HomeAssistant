package is.symphony.FellowDev;

import android.app.Application;
import android.content.Context;
import com.facebook.react.PackageList;
import com.facebook.react.ReactApplication;
import com.facebook.react.ReactHost;
import com.facebook.react.ReactNativeApplicationEntryPoint;
import com.facebook.react.ReactNativeHost;
import com.facebook.react.ReactPackage;
import com.facebook.react.defaults.DefaultReactHost;
import com.facebook.react.defaults.DefaultReactNativeHost;
import com.google.firebase.analytics.FirebaseAnalytics;
import java.util.ArrayList;
import java.util.List;
import kotlin.Metadata;
import kotlin.jvm.internal.Intrinsics;

/* JADX INFO: compiled from: MainApplication.kt */
/* JADX INFO: loaded from: classes3.dex */
@Metadata(d1 = {"\u0000&\n\u0002\u0018\u0002\n\u0002\u0018\u0002\n\u0002\u0018\u0002\n\u0002\b\u0003\n\u0002\u0018\u0002\n\u0002\b\u0003\n\u0002\u0018\u0002\n\u0002\b\u0003\n\u0002\u0010\u0002\n\u0000\u0018\u00002\u00020\u00012\u00020\u0002B\u0007¢\u0006\u0004\b\u0003\u0010\u0004J\b\u0010\r\u001a\u00020\u000eH\u0016R\u0014\u0010\u0005\u001a\u00020\u0006X\u0096\u0004¢\u0006\b\n\u0000\u001a\u0004\b\u0007\u0010\bR\u0014\u0010\t\u001a\u00020\n8VX\u0096\u0004¢\u0006\u0006\u001a\u0004\b\u000b\u0010\f¨\u0006\u000f"}, d2 = {"Lis/symphony/FellowDev/MainApplication;", "Landroid/app/Application;", "Lcom/facebook/react/ReactApplication;", "<init>", "()V", "reactNativeHost", "Lcom/facebook/react/ReactNativeHost;", "getReactNativeHost", "()Lcom/facebook/react/ReactNativeHost;", "reactHost", "Lcom/facebook/react/ReactHost;", "getReactHost", "()Lcom/facebook/react/ReactHost;", "onCreate", "", "app_productionRelease"}, k = 1, mv = {2, 1, 0}, xi = 48)
public final class MainApplication extends Application implements ReactApplication {
    private final ReactNativeHost reactNativeHost = new DefaultReactNativeHost(this) { // from class: is.symphony.FellowDev.MainApplication$reactNativeHost$1
        private final boolean isHermesEnabled;
        private final boolean isNewArchEnabled;

        @Override // com.facebook.react.ReactNativeHost
        public boolean getUseDeveloperSupport() {
            return false;
        }

        {
            super(this);
            this.isNewArchEnabled = true;
            this.isHermesEnabled = true;
        }

        @Override // com.facebook.react.ReactNativeHost
        protected List<ReactPackage> getPackages() {
            ArrayList<ReactPackage> packages = new PackageList(this).getPackages();
            Intrinsics.checkNotNullExpressionValue(packages, "apply(...)");
            return packages;
        }

        @Override // com.facebook.react.ReactNativeHost
        protected String getJSMainModuleName() {
            return FirebaseAnalytics.Param.INDEX;
        }

        @Override // com.facebook.react.defaults.DefaultReactNativeHost
        /* JADX INFO: renamed from: isNewArchEnabled, reason: from getter */
        protected boolean getIsNewArchEnabled() {
            return this.isNewArchEnabled;
        }

        @Override // com.facebook.react.defaults.DefaultReactNativeHost
        protected Boolean isHermesEnabled() {
            return Boolean.valueOf(this.isHermesEnabled);
        }
    };

    @Override // com.facebook.react.ReactApplication
    public ReactNativeHost getReactNativeHost() {
        return this.reactNativeHost;
    }

    @Override // com.facebook.react.ReactApplication
    public ReactHost getReactHost() {
        Context applicationContext = getApplicationContext();
        Intrinsics.checkNotNullExpressionValue(applicationContext, "getApplicationContext(...)");
        return DefaultReactHost.getDefaultReactHost$default(applicationContext, getReactNativeHost(), null, 4, null);
    }

    @Override // android.app.Application
    public void onCreate() {
        super.onCreate();
        ReactNativeApplicationEntryPoint.loadReactNative(this);
    }
}

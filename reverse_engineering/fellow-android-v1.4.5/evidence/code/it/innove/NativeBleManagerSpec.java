package it.innove;

import com.facebook.react.bridge.Callback;
import com.facebook.react.bridge.ReactApplicationContext;
import com.facebook.react.bridge.ReactContextBaseJavaModule;
import com.facebook.react.bridge.ReactMethod;
import com.facebook.react.bridge.ReadableArray;
import com.facebook.react.bridge.ReadableMap;
import com.facebook.react.turbomodule.core.interfaces.TurboModule;
import javax.annotation.Nonnull;

/* JADX INFO: loaded from: classes3.dex */
public abstract class NativeBleManagerSpec extends ReactContextBaseJavaModule implements TurboModule {
    public static final String NAME = "BleManager";

    @ReactMethod
    public abstract void checkState(Callback callback);

    @ReactMethod
    public abstract void companionScan(ReadableArray readableArray, ReadableMap readableMap, Callback callback);

    @ReactMethod
    public abstract void connect(String str, ReadableMap readableMap, Callback callback);

    @ReactMethod
    public abstract void createBond(String str, String str2, Callback callback);

    @ReactMethod
    public abstract void disconnect(String str, boolean z, Callback callback);

    @ReactMethod
    public abstract void enableBluetooth(Callback callback);

    @ReactMethod
    public abstract void getAssociatedPeripherals(Callback callback);

    @ReactMethod
    public abstract void getBondedPeripherals(Callback callback);

    @ReactMethod
    public abstract void getConnectedPeripherals(ReadableArray readableArray, Callback callback);

    @ReactMethod
    public abstract void getDiscoveredPeripherals(Callback callback);

    @ReactMethod
    public abstract void getMaximumWriteValueLengthForWithResponse(String str, Callback callback);

    @ReactMethod
    public abstract void getMaximumWriteValueLengthForWithoutResponse(String str, Callback callback);

    @ReactMethod
    public abstract void isPeripheralConnected(String str, Callback callback);

    @ReactMethod
    public abstract void isScanning(Callback callback);

    @ReactMethod
    public abstract void isStarted(Callback callback);

    @ReactMethod
    public abstract void read(String str, String str2, String str3, Callback callback);

    @ReactMethod
    public abstract void readDescriptor(String str, String str2, String str3, String str4, Callback callback);

    @ReactMethod
    public abstract void readRSSI(String str, Callback callback);

    @ReactMethod
    public abstract void refreshCache(String str, Callback callback);

    @ReactMethod
    public abstract void removeAssociatedPeripheral(String str, Callback callback);

    @ReactMethod
    public abstract void removeBond(String str, Callback callback);

    @ReactMethod
    public abstract void removePeripheral(String str, Callback callback);

    @ReactMethod
    public abstract void requestConnectionPriority(String str, double d, Callback callback);

    @ReactMethod
    public abstract void requestMTU(String str, double d, Callback callback);

    @ReactMethod
    public abstract void retrieveServices(String str, ReadableArray readableArray, Callback callback);

    @ReactMethod
    public abstract void scan(ReadableMap readableMap, Callback callback);

    @ReactMethod
    public abstract void setName(String str);

    @ReactMethod
    public abstract void start(ReadableMap readableMap, Callback callback);

    @ReactMethod
    public abstract void startNotification(String str, String str2, String str3, Callback callback);

    @ReactMethod
    public abstract void startNotificationWithBuffer(String str, String str2, String str3, double d, Callback callback);

    @ReactMethod
    public abstract void stopNotification(String str, String str2, String str3, Callback callback);

    @ReactMethod
    public abstract void stopScan(Callback callback);

    @ReactMethod
    public abstract void supportsCompanion(Callback callback);

    @ReactMethod
    public abstract void write(String str, String str2, String str3, ReadableArray readableArray, double d, Callback callback);

    @ReactMethod
    public abstract void writeDescriptor(String str, String str2, String str3, String str4, ReadableArray readableArray, Callback callback);

    @ReactMethod
    public abstract void writeWithoutResponse(String str, String str2, String str3, ReadableArray readableArray, double d, double d2, Callback callback);

    public NativeBleManagerSpec(ReactApplicationContext reactApplicationContext) {
        super(reactApplicationContext);
    }

    @Override // com.facebook.react.bridge.NativeModule
    @Nonnull
    public String getName() {
        return NAME;
    }

    protected final void emitOnDiscoverPeripheral(ReadableMap readableMap) {
        this.mEventEmitterCallback.invoke("onDiscoverPeripheral", readableMap);
    }

    protected final void emitOnStopScan(ReadableMap readableMap) {
        this.mEventEmitterCallback.invoke("onStopScan", readableMap);
    }

    protected final void emitOnDidUpdateState(ReadableMap readableMap) {
        this.mEventEmitterCallback.invoke("onDidUpdateState", readableMap);
    }

    protected final void emitOnDidUpdateValueForCharacteristic(ReadableMap readableMap) {
        this.mEventEmitterCallback.invoke("onDidUpdateValueForCharacteristic", readableMap);
    }

    protected final void emitOnConnectPeripheral(ReadableMap readableMap) {
        this.mEventEmitterCallback.invoke("onConnectPeripheral", readableMap);
    }

    protected final void emitOnDisconnectPeripheral(ReadableMap readableMap) {
        this.mEventEmitterCallback.invoke("onDisconnectPeripheral", readableMap);
    }

    protected final void emitOnPeripheralDidBond(ReadableMap readableMap) {
        this.mEventEmitterCallback.invoke("onPeripheralDidBond", readableMap);
    }

    protected final void emitOnCentralManagerWillRestoreState(ReadableMap readableMap) {
        this.mEventEmitterCallback.invoke("onCentralManagerWillRestoreState", readableMap);
    }

    protected final void emitOnDidUpdateNotificationStateFor(ReadableMap readableMap) {
        this.mEventEmitterCallback.invoke("onDidUpdateNotificationStateFor", readableMap);
    }

    protected final void emitOnCompanionPeripheral(ReadableMap readableMap) {
        this.mEventEmitterCallback.invoke("onCompanionPeripheral", readableMap);
    }

    protected final void emitOnCompanionFailure(ReadableMap readableMap) {
        this.mEventEmitterCallback.invoke("onCompanionFailure", readableMap);
    }
}

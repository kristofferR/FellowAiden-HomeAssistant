package it.innove;

import android.app.Activity;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.le.ScanFilter;
import android.bluetooth.le.ScanResult;
import android.companion.AssociationRequest;
import android.companion.BluetoothLeDeviceFilter;
import android.companion.CompanionDeviceManager;
import android.content.Intent;
import android.content.IntentSender;
import android.os.Build;
import android.os.Handler;
import android.os.ParcelUuid;
import android.os.Parcelable;
import android.util.Log;
import com.facebook.react.bridge.ActivityEventListener;
import com.facebook.react.bridge.Arguments;
import com.facebook.react.bridge.BaseActivityEventListener;
import com.facebook.react.bridge.Callback;
import com.facebook.react.bridge.ReactApplicationContext;
import com.facebook.react.bridge.ReactContext;
import com.facebook.react.bridge.ReadableArray;
import com.facebook.react.bridge.ReadableMap;
import com.facebook.react.bridge.WritableMap;
import com.google.firebase.messaging.Constants;

/* JADX INFO: loaded from: classes3.dex */
public class CompanionScanner {
    public static final String LOG_TAG = "RNBleManager_Companion";
    private static final int SELECT_DEVICE_REQUEST_CODE = 540;
    private static Callback scanCallback;
    private final BleManager bleManager;
    private final ActivityEventListener mActivityEventListener;
    private final ReactContext reactContext;

    public CompanionScanner(ReactApplicationContext reactApplicationContext, BleManager bleManager) {
        BaseActivityEventListener baseActivityEventListener = new BaseActivityEventListener() { // from class: it.innove.CompanionScanner.1
            /* JADX WARN: Code duplicated, block: B:26:0x0098  */
            /* JADX WARN: Code duplicated, block: B:28:0x009e  */
            /* JADX WARN: Code duplicated, block: B:29:0x00a3  */
            /* JADX WARN: Code duplicated, block: B:33:0x00b6  */
            @Override // com.facebook.react.bridge.BaseActivityEventListener, com.facebook.react.bridge.ActivityEventListener
            public void onActivityResult(Activity activity, int i, int i2, Intent intent) {
                Peripheral peripheralSavePeripheral;
                WritableMap writableMapAsWritableMap;
                Log.d(CompanionScanner.LOG_TAG, "onActivityResult");
                if (i != CompanionScanner.SELECT_DEVICE_REQUEST_CODE) {
                    super.onActivityResult(activity, i, i2, intent);
                    return;
                }
                if (i2 == -1) {
                    Log.d(CompanionScanner.LOG_TAG, "Ok activity result");
                    Parcelable parcelableExtra = intent.getParcelableExtra("android.companion.extra.DEVICE");
                    if (parcelableExtra != null) {
                        if (parcelableExtra instanceof BluetoothDevice) {
                            peripheralSavePeripheral = CompanionScanner.this.bleManager.savePeripheral((BluetoothDevice) parcelableExtra);
                        } else if (parcelableExtra instanceof ScanResult) {
                            peripheralSavePeripheral = CompanionScanner.this.bleManager.savePeripheral(((ScanResult) parcelableExtra).getDevice());
                        } else {
                            Log.wtf(CompanionScanner.LOG_TAG, "Unexpected AssociationInfo device!");
                            peripheralSavePeripheral = null;
                        }
                        if (peripheralSavePeripheral != null && CompanionScanner.scanCallback != null) {
                            CompanionScanner.scanCallback.invoke(null, peripheralSavePeripheral.asWritableMap());
                            CompanionScanner.scanCallback = null;
                            CompanionScanner.this.bleManager.emitOnCompanionPeripheral(peripheralSavePeripheral.asWritableMap());
                        }
                    } else {
                        CompanionScanner.scanCallback.invoke(null, null);
                        CompanionScanner.scanCallback = null;
                        CompanionScanner.this.bleManager.emitOnCompanionPeripheral(null);
                    }
                    if (CompanionScanner.scanCallback != null) {
                        Callback callback = CompanionScanner.scanCallback;
                        if (peripheralSavePeripheral != null) {
                            writableMapAsWritableMap = peripheralSavePeripheral.asWritableMap();
                        } else {
                            writableMapAsWritableMap = null;
                        }
                        callback.invoke(null, writableMapAsWritableMap);
                        CompanionScanner.scanCallback = null;
                    }
                    CompanionScanner.this.bleManager.emitOnCompanionPeripheral(peripheralSavePeripheral != null ? peripheralSavePeripheral.asWritableMap() : null);
                }
                Log.d(CompanionScanner.LOG_TAG, "Non-ok activity result");
                peripheralSavePeripheral = null;
                if (CompanionScanner.scanCallback != null) {
                    Callback callback2 = CompanionScanner.scanCallback;
                    if (peripheralSavePeripheral != null) {
                        writableMapAsWritableMap = peripheralSavePeripheral.asWritableMap();
                    } else {
                        writableMapAsWritableMap = null;
                    }
                    callback2.invoke(null, writableMapAsWritableMap);
                    CompanionScanner.scanCallback = null;
                }
                CompanionScanner.this.bleManager.emitOnCompanionPeripheral(peripheralSavePeripheral != null ? peripheralSavePeripheral.asWritableMap() : null);
            }
        };
        this.mActivityEventListener = baseActivityEventListener;
        this.reactContext = reactApplicationContext;
        this.bleManager = bleManager;
        reactApplicationContext.addActivityEventListener(baseActivityEventListener);
    }

    public void scan(ReadableArray readableArray, ReadableMap readableMap, Callback callback) {
        Log.d(LOG_TAG, "companion scan start");
        if (Build.VERSION.SDK_INT < 26) {
            callback.invoke("Companion not supported");
            return;
        }
        AssociationRequest.Builder singleDevice = new AssociationRequest.Builder().setSingleDevice(readableMap.hasKey("single") && readableMap.getBoolean("single"));
        for (int i = 0; i < readableArray.size(); i++) {
            ParcelUuid parcelUuid = new ParcelUuid(UUIDHelper.uuidFromString(readableArray.getString(i)));
            Log.d(LOG_TAG, "Filter service: " + parcelUuid);
            singleDevice = singleDevice.addDeviceFilter(new BluetoothLeDeviceFilter.Builder().setScanFilter(new ScanFilter.Builder().setServiceUuid(parcelUuid).build()).build());
        }
        AssociationRequest associationRequestBuild = singleDevice.build();
        Callback callback2 = scanCallback;
        if (callback2 != null) {
            callback2.invoke("New scan called", null);
        }
        scanCallback = callback;
        ((CompanionDeviceManager) this.bleManager.getCompanionDeviceManager()).associate(associationRequestBuild, new CompanionDeviceManager.Callback() { // from class: it.innove.CompanionScanner.2
            @Override // android.companion.CompanionDeviceManager.Callback
            public void onFailure(CharSequence charSequence) {
                String str;
                Log.d(CompanionScanner.LOG_TAG, "companion failure: " + ((Object) charSequence));
                if (charSequence != null) {
                    str = "Companion association failed: " + charSequence.toString();
                } else {
                    str = "Companion association failed";
                }
                if (CompanionScanner.scanCallback != null) {
                    CompanionScanner.scanCallback.invoke(str);
                    CompanionScanner.scanCallback = null;
                }
                WritableMap writableMapCreateMap = Arguments.createMap();
                writableMapCreateMap.putString(Constants.IPC_BUNDLE_KEY_SEND_ERROR, charSequence.toString());
                CompanionScanner.this.bleManager.emitOnCompanionFailure(writableMapCreateMap);
            }

            @Override // android.companion.CompanionDeviceManager.Callback
            public void onDeviceFound(IntentSender intentSender) {
                Log.d(CompanionScanner.LOG_TAG, "companion device found");
                try {
                    CompanionScanner.this.reactContext.getCurrentActivity().startIntentSenderForResult(intentSender, CompanionScanner.SELECT_DEVICE_REQUEST_CODE, null, 0, 0, 0);
                } catch (IntentSender.SendIntentException e) {
                    Log.e(CompanionScanner.LOG_TAG, "Failed to send intent: " + e.toString());
                    String str = "Failed to send intent: " + e.toString();
                    if (CompanionScanner.scanCallback != null) {
                        CompanionScanner.scanCallback.invoke(str);
                        CompanionScanner.scanCallback = null;
                    }
                    WritableMap writableMapCreateMap = Arguments.createMap();
                    writableMapCreateMap.putString(Constants.IPC_BUNDLE_KEY_SEND_ERROR, str);
                    CompanionScanner.this.bleManager.emitOnCompanionFailure(writableMapCreateMap);
                }
            }
        }, (Handler) null);
    }
}

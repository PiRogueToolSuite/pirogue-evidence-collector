function _log_ad_ids() {
    try {
        const client = Java.use('com.google.android.gms.ads.identifier.AdvertisingIdClient');
        client.getAdvertisingIdInfo.overload('android.content.Context').implementation = function (x) {
            const i = this.getAdvertisingIdInfo(x);
            const id = i.getId();
            const msg = {
                'type': 'advertising_id_log',
                'dump': 'ad_ids.txt',
                'data_type': 'plain',
                'data': id
            }
            console.log(`Advertising ID requested: ${id}`)
            send(msg);
            return i;
        };
    } catch (e) {
    }
}

export function log_ad_ids() {
    Java.perform(() => {
        _log_ad_ids();
    });
}
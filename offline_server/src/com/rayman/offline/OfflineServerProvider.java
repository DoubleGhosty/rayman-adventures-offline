package com.rayman.offline;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.net.Uri;

/**
 * Declared in AndroidManifest.xml so that Android instantiates it automatically
 * at process start (before any Activity). Its only job is to start the embedded
 * mock server that replaces the shut-down Ubisoft services.
 */
public class OfflineServerProvider extends ContentProvider {

    @Override
    public boolean onCreate() {
        OfflineServer.start(getContext());
        return true;
    }

    @Override
    public Cursor query(Uri uri, String[] projection, String selection, String[] selectionArgs, String sortOrder) {
        return null;
    }

    @Override
    public String getType(Uri uri) {
        return null;
    }

    @Override
    public Uri insert(Uri uri, ContentValues values) {
        return null;
    }

    @Override
    public int delete(Uri uri, String selection, String[] selectionArgs) {
        return 0;
    }

    @Override
    public int update(Uri uri, ContentValues values, String selection, String[] selectionArgs) {
        return 0;
    }
}

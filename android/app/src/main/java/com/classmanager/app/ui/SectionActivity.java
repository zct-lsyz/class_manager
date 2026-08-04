package com.classmanager.app.ui;

import android.content.Intent;
import android.os.Bundle;
import android.widget.ArrayAdapter;
import android.widget.ListView;

import java.util.List;

public class SectionActivity extends BaseActivity {
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        String section = getIntent().getStringExtra("section");
        List<FeatureCatalog.Entry> entries = FeatureCatalog.sections().get(section);
        setup(section == null ? "功能" : section, true);
        ListView list = new ListView(this);
        if (entries == null) {
            show(list);
            return;
        }
        String[] labels = new String[entries.size()];
        for (int i = 0; i < entries.size(); i++) labels[i] = entries.get(i).title;
        list.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_list_item_1, labels));
        list.setOnItemClickListener((parent, view, position, id) -> open(entries.get(position)));
        show(list);
    }

    private void open(FeatureCatalog.Entry entry) {
        Intent intent;
        if (FeatureCatalog.RESOURCE.equals(entry.kind)) {
            intent = new Intent(this, ResourceActivity.class);
            intent.putExtra("resource", entry.value);
            intent.putExtra("title", entry.title);
        } else if (FeatureCatalog.REPORT.equals(entry.kind)) {
            intent = new Intent(this, ReportActivity.class);
            intent.putExtra("endpoint", entry.value);
            intent.putExtra("title", entry.title);
        } else if (FeatureCatalog.BACKUP.equals(entry.kind)) {
            intent = new Intent(this, BackupActivity.class);
        } else {
            intent = new Intent(this, AccountActivity.class);
        }
        startActivity(intent);
    }
}

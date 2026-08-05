package com.classmanager.app.ui;

import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.ListView;
import android.widget.TextView;

import com.classmanager.app.R;

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
        list.setDivider(new android.graphics.drawable.ColorDrawable(android.graphics.Color.TRANSPARENT));
        list.setDividerHeight(Ui.dp(this, 8));
        list.setPadding(Ui.dp(this, 16), Ui.dp(this, 16), Ui.dp(this, 16), Ui.dp(this, 16));
        list.setClipToPadding(false);
        list.setAdapter(new ArrayAdapter<String>(this, android.R.layout.simple_list_item_1, labels) {
            @Override public View getView(int position, View convertView, ViewGroup parent) {
                View view = super.getView(position, convertView, parent);
                TextView text = view.findViewById(android.R.id.text1);
                text.setText(getString(R.string.module_navigation_item, labels[position]));
                text.setTextColor(getColor(R.color.primary));
                text.setTextSize(16);
                text.setPadding(Ui.dp(SectionActivity.this, 16), Ui.dp(SectionActivity.this, 14), Ui.dp(SectionActivity.this, 16), Ui.dp(SectionActivity.this, 14));
                int[] colors = {0xffe8f0fe, 0xffe8f5e9, 0xfffff3e0, 0xfffce4ec, 0xffede7f6, 0xffe0f7fa};
                text.setBackground(Ui.rounded(SectionActivity.this, colors[position % colors.length], 0, 12));
                return view;
            }
        });
        list.setOnItemClickListener((parent, view, position, id) -> open(entries.get(position)));
        show(list);
    }

    private void open(FeatureCatalog.Entry entry) {
        startActivity(intentFor(this, entry));
    }

    public static Intent intentFor(Context context, FeatureCatalog.Entry entry) {
        Intent intent;
        if (FeatureCatalog.RESOURCE.equals(entry.kind)) {
            intent = new Intent(context, ResourceActivity.class);
            intent.putExtra("resource", entry.value);
            intent.putExtra("title", entry.title);
        } else if (FeatureCatalog.REPORT.equals(entry.kind)) {
            intent = new Intent(context, ReportActivity.class);
            intent.putExtra("endpoint", entry.value);
            intent.putExtra("title", entry.title);
        } else if (FeatureCatalog.BACKUP.equals(entry.kind)) {
            intent = new Intent(context, BackupActivity.class);
        } else if (FeatureCatalog.AI.equals(entry.kind)) {
            intent = new Intent(context, AiAnalysisActivity.class);
        } else if (FeatureCatalog.DORMITORY.equals(entry.kind)) {
            intent = new Intent(context, DormitoryActivity.class);
        } else if (FeatureCatalog.PAPER_AI.equals(entry.kind)) {
            intent = new Intent(context, ExamPaperAnalysisActivity.class);
        } else if (FeatureCatalog.RANKING.equals(entry.kind)) {
            intent = new Intent(context, RankingActivity.class);
        } else {
            intent = new Intent(context, AccountActivity.class);
        }
        return intent;
    }
}

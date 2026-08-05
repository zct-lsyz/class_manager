package com.classmanager.app.ui;

import android.app.ActivityOptions;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.SystemClock;
import android.view.Gravity;
import android.view.MenuItem;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.appcompat.widget.Toolbar;
import androidx.core.view.GravityCompat;
import androidx.drawerlayout.widget.DrawerLayout;

import com.classmanager.app.R;
import com.classmanager.app.data.SessionStore;

import java.util.List;
import java.util.Map;

public abstract class BaseActivity extends AppCompatActivity {
    private static final long EXIT_CONFIRM_WINDOW_MS = 2000L;
    protected FrameLayout content;
    protected DrawerLayout drawer;
    private long lastBackPressedAt;

    protected void setup(String title, boolean showBack) {
        setContentView(R.layout.activity_container);
        Toolbar toolbar = findViewById(R.id.toolbar);
        toolbar.setTitle(title);
        toolbar.setTitleTextColor(Color.WHITE);
        setSupportActionBar(toolbar);
        drawer = findViewById(R.id.drawer_layout);
        if (SessionStore.get(this).isLoggedIn()) {
            toolbar.setNavigationIcon(R.drawable.ic_menu);
            toolbar.setNavigationOnClickListener(view -> drawer.openDrawer(GravityCompat.START));
            MenuItem backItem = toolbar.getMenu().add("返回上一级");
            backItem.setShowAsAction(MenuItem.SHOW_AS_ACTION_ALWAYS | MenuItem.SHOW_AS_ACTION_WITH_TEXT);
            backItem.setOnMenuItemClickListener(item -> {
                onBackPressed();
                return true;
            });
            backItem.setVisible(false);
            TextView toolbarBack = Ui.text(this, "返回上一级");
            toolbarBack.setTextColor(Color.WHITE);
            toolbarBack.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
            toolbarBack.setGravity(Gravity.CENTER);
            toolbarBack.setPadding(Ui.dp(this, 12), 0, Ui.dp(this, 12), 0);
            toolbarBack.setOnClickListener(view -> onBackPressed());
            Toolbar.LayoutParams backParams = new Toolbar.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.MATCH_PARENT);
            backParams.gravity = Gravity.END;
            toolbar.addView(toolbarBack, backParams);
            populateNavigation(title);
        } else if (showBack && getSupportActionBar() != null) {
            getSupportActionBar().setDisplayHomeAsUpEnabled(true);
            toolbar.setNavigationOnClickListener(view -> finish());
        } else {
            drawer.setDrawerLockMode(DrawerLayout.LOCK_MODE_LOCKED_CLOSED);
        }
        content = findViewById(R.id.content);
    }

    private void populateNavigation(String currentTitle) {
        LinearLayout navigation = findViewById(R.id.navigation_items);
        navigation.removeAllViews();
        TextView brand = Ui.title(this, "班级教学管理平台");
        brand.setTextColor(getColor(R.color.primary));
        brand.setPadding(Ui.dp(this, 4), Ui.dp(this, 12), Ui.dp(this, 4), Ui.dp(this, 18));
        navigation.addView(brand);
        addNavigationItem(navigation, "工作台首页", "工作台".equals(currentTitle), 0, view -> {
            drawer.closeDrawer(GravityCompat.START);
            if (!(this instanceof MainActivity)) navigateAsRoot(new Intent(this, MainActivity.class));
        });
        int colorIndex = 1;
        for (Map.Entry<String, List<String>> group : FeatureCatalog.groups().entrySet()) {
            TextView heading = Ui.text(this, group.getKey());
            heading.setTextSize(12);
            heading.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
            heading.setTextColor(getColor(R.color.primary));
            heading.setPadding(Ui.dp(this, 4), Ui.dp(this, 14), Ui.dp(this, 4), Ui.dp(this, 5));
            navigation.addView(heading);
            for (String section : group.getValue()) {
                boolean active = section.equals(currentTitle);
                List<FeatureCatalog.Entry> entries = FeatureCatalog.sections().get(section);
                if (entries != null) for (FeatureCatalog.Entry entry : entries) active |= entry.title.equals(currentTitle);
                addNavigationItem(navigation, section, active, colorIndex++, view -> openNavigation(section));
            }
        }
        TextView bottom = new TextView(this);
        navigation.addView(bottom, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, Ui.dp(this, 24)));
    }

    private void addNavigationItem(LinearLayout parent, String label, boolean active, int colorIndex, View.OnClickListener listener) {
        int[] colors = {0xffe8f0fe, 0xffe8f5e9, 0xfffff3e0, 0xfffce4ec, 0xffede7f6, 0xffe0f7fa};
        TextView item = Ui.text(this, label);
        item.setTextSize(15);
        item.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        item.setTextColor(active ? Color.WHITE : getColor(R.color.primary));
        item.setGravity(Gravity.CENTER_VERTICAL);
        item.setPadding(Ui.dp(this, 14), Ui.dp(this, 11), Ui.dp(this, 14), Ui.dp(this, 11));
        item.setBackground(Ui.rounded(this, active ? getColor(R.color.primary) : colors[colorIndex % colors.length], 0, 12));
        item.setOnClickListener(listener);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        params.setMargins(0, Ui.dp(this, 3), 0, Ui.dp(this, 3));
        parent.addView(item, params);
    }

    private void openNavigation(String section) {
        drawer.closeDrawer(GravityCompat.START);
        List<FeatureCatalog.Entry> entries = FeatureCatalog.sections().get(section);
        if (entries != null && entries.size() == 1) navigateAsRoot(SectionActivity.intentFor(this, entries.get(0)));
        else {
            Intent intent = new Intent(this, SectionActivity.class);
            intent.putExtra("section", section);
            navigateAsRoot(intent);
        }
    }

    private void navigateAsRoot(Intent intent) {
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);
        startActivity(intent, ActivityOptions.makeCustomAnimation(
                this, R.anim.module_enter, R.anim.module_exit).toBundle());
    }

    @Override
    public void onBackPressed() {
        if (drawer != null && drawer.isDrawerOpen(GravityCompat.START)) drawer.closeDrawer(GravityCompat.START);
        else if (this instanceof MainActivity) {
            long now = SystemClock.elapsedRealtime();
            if (isSecondBackPress(lastBackPressedAt, now)) finishAffinity();
            else {
                lastBackPressedAt = now;
                Toast.makeText(this, "再按一次返回键退出", Toast.LENGTH_SHORT).show();
            }
        } else if (SessionStore.get(this).isLoggedIn() && isTaskRoot()) {
            navigateAsRoot(new Intent(this, MainActivity.class));
        } else super.onBackPressed();
    }

    static boolean isSecondBackPress(long previous, long now) {
        return previous > 0 && now >= previous && now - previous <= EXIT_CONFIRM_WINDOW_MS;
    }

    protected void show(View view) {
        content.removeAllViews();
        content.addView(view, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
    }

    protected void toast(String message) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
    }

    protected void handleAuthError(int status) {
        if (status == 401) {
            SessionStore.get(this).clear();
            startActivity(new Intent(this, LoginActivity.class)
                    .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK | Intent.FLAG_ACTIVITY_NEW_TASK));
        }
    }
}

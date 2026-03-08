import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import glob
import os

# ── Colour palette ──────────────────────────────────────────────────
C_RR  = '#E74C3C'   # red  – Round Robin
C_HA  = '#2ECC71'   # green – Hardware Aware
PAL   = {'Round-Robin': C_RR, 'Hardware-Aware': C_HA}

def load_data(pattern):
    """Load all JSON result files and return a DataFrame with strategy & load_type columns."""
    all_data = []
    files = sorted(glob.glob(pattern))
    print(f"Loading {len(files)} result files...")

    for f in files:
        bn = os.path.basename(f).replace('.json', '')
        # Derive strategy and load from filename
        # Handles: results_round-robin_normal_*.json  OR  results_rr_normal.json
        bn_lower = bn.lower()
        if 'round-robin' in bn_lower or '_rr_' in bn_lower:
            strategy = 'Round-Robin'
        elif 'hardware-aware' in bn_lower or '_ha_' in bn_lower:
            strategy = 'Hardware-Aware'
        else:
            strategy = 'Unknown'

        if '_normal' in bn_lower:
            load_type = 'Normal'
        elif '_stress' in bn_lower:
            load_type = 'Stress'
        else:
            load_type = 'Unknown'

        with open(f, 'r') as j:
            try:
                data = json.load(j)
                for entry in data:
                    entry['strategy']  = strategy
                    entry['load_type'] = load_type
                    entry['success']   = (entry.get('status') == 200)
                    all_data.append(entry)
            except Exception as e:
                print(f"  ⚠ Error loading {f}: {e}")

    df = pd.DataFrame(all_data)
    print(f"  Total records: {len(df)}")
    return df

# ── Helper: annotate bars ───────────────────────────────────────────
def _label_bars(ax, fmt='{:.1f}', suffix=''):
    for p in ax.patches:
        h = p.get_height()
        if h > 0:
            ax.text(p.get_x() + p.get_width()/2., h,
                    fmt.format(h) + suffix,
                    ha='center', va='bottom', fontsize=10, fontweight='bold')

# ── Plot 1: Success Rate ───────────────────────────────────────────
def plot_success_rate(df, out):
    sr = df.groupby(['load_type', 'strategy'])['success'].mean() * 100
    sr = sr.unstack('strategy').reindex(['Normal', 'Stress'])
    sr = sr[['Round-Robin', 'Hardware-Aware']]

    fig, ax = plt.subplots(figsize=(9, 6))
    sr.plot.bar(ax=ax, color=[C_RR, C_HA], edgecolor='white', width=0.6)
    ax.set_ylim(0, 115)
    ax.set_ylabel('Success Rate (%)', fontsize=12)
    ax.set_xlabel('')
    ax.set_title('Request Success Rate by Strategy & Load', fontsize=15, pad=15)
    ax.legend(title='Strategy')
    ax.set_xticklabels(ax.get_xticklabels(), rotation=0)
    _label_bars(ax, suffix='%')
    plt.tight_layout()
    plt.savefig(f'{out}/success_rate.png', dpi=300)
    plt.close()
    print('  ✓ success_rate.png')

# ── Plot 2: Latency bar chart (mean + p95) ─────────────────────────
def plot_latency_bars(df_ok, out):
    stats = df_ok.groupby(['load_type', 'strategy'])['latency_ms'].agg(
        Mean='mean',
        p95=lambda x: x.quantile(0.95)
    ).reset_index()

    fig, axes = plt.subplots(1, 2, figsize=(16, 6), sharey=False)

    for i, metric in enumerate(['Mean', 'p95']):
        ax = axes[i]
        subset = stats.pivot(index='load_type', columns='strategy', values=metric)
        subset = subset.reindex(['Normal', 'Stress'])[['Round-Robin', 'Hardware-Aware']]
        subset.plot.bar(ax=ax, color=[C_RR, C_HA], edgecolor='white', width=0.6)
        ax.set_title(f'{metric} Latency (ms)', fontsize=14)
        ax.set_ylabel('Latency (ms)')
        ax.set_xlabel('')
        ax.set_xticklabels(ax.get_xticklabels(), rotation=0)
        _label_bars(ax, fmt='{:.1f}', suffix=' ms')
        ax.legend(title='Strategy')

    fig.suptitle('Latency Comparison: Round-Robin vs Hardware-Aware', fontsize=16, y=1.02)
    plt.tight_layout()
    plt.savefig(f'{out}/latency_comparison.png', dpi=300)
    plt.close()
    print('  ✓ latency_comparison.png')

# ── Plot 3: FacetGrid KDE Density (latency_distribution style) ─────
def plot_latency_distribution(df_ok, out):
    import seaborn as sns
    sns.set_theme(style="whitegrid")

    # Map strategy names to lowercase for legend consistency
    plot_df = df_ok.copy()
    plot_df['Strategy'] = plot_df['strategy']
    plot_df['load_type_label'] = plot_df['load_type'].str.lower()

    g = sns.FacetGrid(plot_df, col='load_type_label', hue='Strategy',
                      col_order=['normal', 'stress'],
                      hue_order=['Hardware-Aware', 'Round-Robin'],
                      palette={'Hardware-Aware': C_HA, 'Round-Robin': C_RR},
                      height=5, aspect=1.3)
    g.map(sns.kdeplot, 'latency_ms', fill=True, alpha=0.35, common_norm=False)
    g.add_legend(title='Strategy')
    g.set_axis_labels('Latency (ms)', 'Density')
    g.set_titles('load_type = {col_name}')
    g.fig.subplots_adjust(top=0.88)
    g.fig.suptitle('Inference Latency Distribution: Normal vs Stress', fontsize=16)
    g.savefig(f'{out}/latency_distribution.png', dpi=300)
    plt.close('all')
    print('  ✓ latency_distribution.png')

# ── Plot 4: Individual histogram per (strategy, load) ──────────────
def plot_individual(df_ok, out):
    combos = [
        ('Round-Robin',    'Normal',  'latency_rr_normal.png'),
        ('Round-Robin',    'Stress',  'latency_rr_stress.png'),
        ('Hardware-Aware', 'Normal',  'latency_ha_normal.png'),
        ('Hardware-Aware', 'Stress',  'latency_ha_stress.png'),
    ]
    for strat, load, fname in combos:
        sub = df_ok[(df_ok['strategy'] == strat) & (df_ok['load_type'] == load)]
        if sub.empty:
            print(f'  ⚠ No data for {strat} / {load}')
            continue

        fig, ax = plt.subplots(figsize=(10, 6))
        color = C_RR if strat == 'Round-Robin' else C_HA

        ax.hist(sub['latency_ms'], bins=20, color=color, alpha=0.7, edgecolor='white')

        mean_v = sub['latency_ms'].mean()
        p95_v  = sub['latency_ms'].quantile(0.95)
        ax.axvline(mean_v, color='black', ls='--', lw=2, label=f'Mean: {mean_v:.1f} ms')
        ax.axvline(p95_v,  color='orange', ls='-',  lw=2, label=f'p95:  {p95_v:.1f} ms')

        ax.set_title(f'{strat}  —  {load} Load', fontsize=15, pad=12)
        ax.set_xlabel('Latency (ms)', fontsize=12)
        ax.set_ylabel('Request Count', fontsize=12)
        ax.legend(fontsize=11)
        plt.tight_layout()
        plt.savefig(f'{out}/{fname}', dpi=300)
        plt.close()
        print(f'  ✓ {fname}')

# ── Plot 4: Global Dashboard (2-panel) ─────────────────────────────
def plot_dashboard(df, df_ok, out):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 7))

    # Panel A – success rate
    sr = df.groupby(['load_type', 'strategy'])['success'].mean() * 100
    sr = sr.unstack('strategy').reindex(['Normal', 'Stress'])[['Round-Robin', 'Hardware-Aware']]
    sr.plot.bar(ax=ax1, color=[C_RR, C_HA], edgecolor='white', width=0.6)
    ax1.set_ylim(0, 115)
    ax1.set_title('A: System Reliability (Success %)', fontsize=14)
    ax1.set_ylabel('Success Rate (%)')
    ax1.set_xlabel('')
    ax1.set_xticklabels(ax1.get_xticklabels(), rotation=0)
    ax1.legend(title='Strategy')
    _label_bars(ax1, suffix='%')

    # Panel B – p95 latency
    p95 = df_ok.groupby(['load_type', 'strategy'])['latency_ms'].quantile(0.95)
    p95 = p95.unstack('strategy').reindex(['Normal', 'Stress'])[['Round-Robin', 'Hardware-Aware']]
    p95.plot.bar(ax=ax2, color=[C_RR, C_HA], edgecolor='white', width=0.6)
    ax2.set_title('B: Tail Latency — p95 (ms)', fontsize=14)
    ax2.set_ylabel('p95 Latency (ms)')
    ax2.set_xlabel('')
    ax2.set_xticklabels(ax2.get_xticklabels(), rotation=0)
    ax2.legend(title='Strategy')
    _label_bars(ax2, suffix=' ms')

    fig.suptitle('Global Performance Dashboard: Static vs Hardware-Aware Routing',
                 fontsize=17, y=1.02)
    plt.tight_layout()
    plt.savefig(f'{out}/global_dashboard.png', dpi=300)
    plt.close()
    print('  ✓ global_dashboard.png')

# ── Plot 6: Breaking-Point Analysis ────────────────────────────────
def plot_breaking_point(out='plots'):
    """Load breaking_point_*.json summaries and plot success rate + latency vs concurrency."""
    import glob as _glob
    files = sorted(_glob.glob('group22_results/group22_breaking_point_*.json'))
    if not files:
        return  # No breaking-point data

    fig, ax1 = plt.subplots(figsize=(12, 7))
    ax2 = ax1.twinx()

    colors_sr  = {'Round-Robin': C_RR, 'Hardware-Aware': C_HA,
                  'round-robin': C_RR, 'hardware-aware': C_HA,
                  'rr': C_RR, 'ha': C_HA}
    
    for f in files:
        bn = os.path.basename(f).lower()
        if 'round-robin' in bn or '_rr_' in bn:
            label = 'Round-Robin'
        elif 'hardware-aware' in bn or '_ha_' in bn:
            label = 'Hardware-Aware'
        else:
            label = os.path.basename(f)

        with open(f) as j:
            waves = json.load(j)

        conc    = [w['concurrency'] for w in waves]
        sr      = [w['success_rate'] for w in waves]
        mean_l  = [w['mean_latency_ms'] for w in waves]

        c = colors_sr.get(label, '#888888')

        # Success rate line (left y-axis)
        ax1.plot(conc, sr, 'o-', color=c, linewidth=2.5, markersize=8, label=f'{label} (Success %)')

        # Mean latency line (right y-axis)
        ax2.plot(conc, mean_l, 's--', color=c, linewidth=1.5, markersize=6, alpha=0.6,
                 label=f'{label} (Mean Latency)')

    ax1.set_xlabel('Concurrent Requests', fontsize=13)
    ax1.set_ylabel('Success Rate (%)', fontsize=13, color='black')
    ax1.set_ylim(0, 110)
    ax1.axhline(50, color='gray', ls=':', lw=1, alpha=0.5)
    ax1.legend(loc='lower left', fontsize=10)

    ax2.set_ylabel('Mean Latency (ms)', fontsize=13, color='gray')
    ax2.legend(loc='upper right', fontsize=10)

    plt.title('Breaking-Point Analysis: Load Ramp Until Failure', fontsize=16, pad=15)
    plt.tight_layout()
    plt.savefig(f'{out}/breaking_point.png', dpi=300)
    plt.close()
    print('  ✓ breaking_point.png')

# ── Main ────────────────────────────────────────────────────────────
def generate_all(pattern='group22_results/group22_results_*.json', out='group22_plots'):
    df = load_data(pattern)
    if df.empty:
        print('No data found.')
        return

    os.makedirs(out, exist_ok=True)

    # Successful-only subset for latency charts
    df_ok = df[df['success'] == True].copy()

    # Filter out breaking-point data from standard plots
    df_std    = df[~df['load_type'].str.contains('breaking', case=False, na=False)]
    df_std_ok = df_ok[~df_ok['load_type'].str.contains('breaking', case=False, na=False)]

    if not df_std.empty:
        plot_success_rate(df_std, out)
        plot_latency_bars(df_std_ok, out)
        plot_latency_distribution(df_std_ok, out)
        plot_individual(df_std_ok, out)
        plot_dashboard(df_std, df_std_ok, out)

    # Breaking-point plot (uses its own JSON files)
    plot_breaking_point(out)

    # Print summary table
    print('\n── Summary ──')
    for (s, l), g in df.groupby(['strategy', 'load_type']):
        ok = g[g['success']]
        sr = len(ok)/len(g)*100 if len(g) else 0
        print(f'  {s:16s} | {l:6s} | SR={sr:5.1f}%  '
              f'Mean={ok["latency_ms"].mean():7.1f}ms  '
              f'p95={ok["latency_ms"].quantile(0.95):7.1f}ms')

if __name__ == '__main__':
    generate_all()

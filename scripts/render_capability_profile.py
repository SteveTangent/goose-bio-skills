#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check the reviewed inventory; optionally rebuild the README radar and table."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'docs/data/capability-profile.json'
DOC = ROOT / 'docs/capability-profile.md'
START, END = '<!-- capability-table:start -->', '<!-- capability-table:end -->'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_review():
    data = json.loads(DATA.read_text())
    registry = json.loads((ROOT / 'registry.json').read_text())
    if data['registry_sha256'] != digest(ROOT / 'registry.json'):
        raise ValueError('Registry changed: review scope/stages and refresh the inventory first.')
    actual = {s['name']: s for s in registry['skills']}
    seen = set()
    domains = data['domains']
    if [d['id'] for d in domains] != sorted({s['domain_id'] for s in actual.values()}):
        raise ValueError('Domain inventory differs from the registry.')
    for domain in domains:
        if type(domain['stage']) is not int or not 0 <= domain['stage'] <= 5:
            raise ValueError('Capability stages must be integers in 0..5.')
        if not all(domain[k].strip() for k in ('label_zh', 'chart_label', 'rationale', 'limits', 'next')):
            raise ValueError('Every domain needs scope, limits and reasoning.')
        for skill in domain['skills']:
            name = skill['name']
            if name not in actual or name in seen:
                raise ValueError('Unknown or repeated Skill: ' + name)
            seen.add(name)
            entry = actual[name]
            path = ROOT / entry['path']
            manifest = json.loads((path / 'manifest.json').read_text())
            if (entry['domain_id'] != domain['id']
                    or entry['package_digest'] != skill['package_digest']
                    or digest(path / 'manifest.json') != skill['manifest_sha256']
                    or manifest['script_verification']['bundled_scripts'] != skill['has_helper']
                    or len(list((path / 'scripts').glob('*.py'))) != skill['helper_count']):
                raise ValueError('Stale capability inventory: ' + name)
    if seen != set(actual):
        raise ValueError('Every current Skill must appear exactly once.')
    return data


def table(data):
    lines = ['| 领域 | Skill / helper | 阶段（0–5） | 评分依据 | 主要边界 |',
             '| --- | ---: | ---: | --- | --- |']
    for d in data['domains']:
        n = len(d['skills'])
        h = sum(s['helper_count'] for s in d['skills'])
        lines.append(f"| {d['id']} {d['label_zh']} | {n} / {h} | {d['stage']} | {d['rationale']} | {d['limits']} |")
    return '\n'.join(lines)


def render(data):
    # Plotting dependencies are optional; --check uses only the standard library.
    import math
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    plt.rcParams.update({'font.family': 'DejaVu Sans', 'svg.hashsalt': 'goose-capability-v1'})
    domains = data['domains']
    angles = [2 * math.pi * i / len(domains) for i in range(len(domains))]
    values = [d['stage'] for d in domains]
    fig = plt.figure(figsize=(13.5, 9), facecolor='#f8faf9')
    ax = fig.add_axes([.13, .18, .53, .56], projection='polar', facecolor='#f8faf9')
    ax.set_theta_offset(math.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_ylim(0, 5)
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.set_yticklabels(['1', '2', '3', '4', '5'], fontsize=8, color='#6b7c80')
    ax.set_rlabel_position(5)
    ax.set_xticks(angles)
    ax.set_xticklabels([d['chart_label'] for d in domains], fontsize=10, color='#223c40')
    ax.tick_params(axis='x', pad=19)
    ax.grid(color='#c8d7d5', linewidth=.75)
    ax.spines['polar'].set_color('#bdcfcc')
    ax.plot(angles + angles[:1], values + values[:1], color='#087f80', linewidth=2.5)
    ax.fill(angles + angles[:1], values + values[:1], color='#087f80', alpha=.14)
    ax.scatter(angles, values, color='#087f80', s=38, zorder=5)
    for a, v in zip(angles, values):
        ax.text(a, v + .28, str(v), ha='center', va='center', color='#075657',
                fontsize=10, weight='bold', bbox={'facecolor': '#f8faf9', 'edgecolor': 'none', 'pad': 1})
    fig.text(.075, .94, 'GOOSE BIO SKILLS', color='#087f80', fontsize=11, weight='bold')
    fig.text(.075, .895, 'Where the library can help today', color='#18373b', fontsize=25, weight='bold')
    fig.text(.075, .855, 'A scope-based capability profile of the main preview', color='#526b70', fontsize=12)
    n = sum(len(d['skills']) for d in domains)
    h = sum(s['helper_count'] for d in domains for s in d['skills'])
    fig.text(.77, .76, f'{n} Skills\n{h} bounded helpers\n{len(domains)} domains', fontsize=17,
             color='#18373b', linespacing=1.7, weight='bold')
    fig.text(.77, .53, 'CAPABILITY STAGE', fontsize=10, color='#087f80', weight='bold')
    labels = ['0  No coverage', '1  Guidance', '2  Preparation / QC / retrieval', '3  Bounded analysis',
              '4  Connected small-data path', '5  Multiple connected paths']
    for i, label in enumerate(labels):
        fig.text(.77, .49 - i * .036, label, fontsize=10, color='#39565b')
    fig.text(.075, .095, 'Stages are editorial judgments, not accuracy, coverage percentages or benchmark scores.',
             fontsize=10, color='#526b70')
    fig.text(.075, .063, f"Reviewed {data['reviewed_at']}  |  Narrow task boundaries apply  |  No overall score or polygon-area ranking",
             fontsize=9, color='#526b70')
    output = ROOT / 'assets/figures'
    output.mkdir(exist_ok=True, parents=True)
    fig.savefig(output / 'capability-radar.svg', metadata={'Date': None, 'Creator': 'Goose Bio Skills'}, facecolor=fig.get_facecolor())
    fig.savefig(output / 'capability-radar.png', dpi=160, metadata={'Software': 'Goose Bio Skills'}, facecolor=fig.get_facecolor())
    plt.close(fig)
    identity = {'data_sha256': digest(DATA), 'files': {f'capability-radar.{suffix}': digest(output / f'capability-radar.{suffix}') for suffix in ('svg', 'png')}}
    (output / 'capability-radar.json').write_text(json.dumps(identity, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Validate inventory and generated table without plotting dependencies.')
    args = parser.parse_args()
    data = load_review()
    content = DOC.read_text()
    if content.count(START) != 1 or content.count(END) != 1:
        raise ValueError('Expected exactly one generated table block.')
    before, rest = content.split(START)
    old, after = rest.split(END)
    expected = '\n\n' + table(data) + '\n\n'
    if args.check:
        if old != expected:
            raise ValueError('Capability table is stale; rebuild after review.')
        output = ROOT / 'assets/figures'
        identity = json.loads((output / 'capability-radar.json').read_text())
        if identity['data_sha256'] != digest(DATA):
            raise ValueError('Radar images belong to an older data review.')
        expected_files = {f'capability-radar.{suffix}' for suffix in ('svg', 'png')}
        if set(identity['files']) != expected_files:
            raise ValueError('Incomplete radar image inventory.')
        for name, sha in identity['files'].items():
            if digest(output / name) != sha:
                raise ValueError('Radar image differs from its rendered fingerprint.')
    else:
        render(data)
        DOC.write_text(before + START + expected + END + after)
    print(json.dumps({'status': 'pass', 'domains': len(data['domains']), 'mode': 'check' if args.check else 'render'}))


if __name__ == '__main__':
    main()

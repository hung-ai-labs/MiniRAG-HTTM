"""Static export of the completed amended evaluation; no model/API access."""
import argparse
import json
from pathlib import Path
import sys


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--plot-dependencies',type=Path)
    args=p.parse_args()
    if args.plot_dependencies:sys.path.insert(0,str(args.plot_dependencies))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font=Path('C:/Windows/Fonts/arial.ttf')
    if font.exists():
        font_manager.fontManager.addfont(str(font));matplotlib.rcParams['font.family']='Arial'
    matplotlib.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False,
        'axes.titlesize':13,'axes.titleweight':'bold','svg.fonttype':'none'})
    d=json.loads(args.results.read_text(encoding='utf-8'))
    if d.get('valid_votes')!=38808 or 'amendment' not in d:raise ValueError('Completed amended result required')
    seeds=['101','202','303'];x=list(range(3));colors={'C0':'#64748b','C1':'#087f8c'}
    fig,axes=plt.subplots(2,2,figsize=(14,9.4))
    def bars(ax,values,title,ylabel,limit):
        for cfg,offset,label in (('C0',-.18,'C0 baseline'),('C1',.18,'B2')):
            heights=values(cfg)
            ax.bar([n+offset for n in x],heights,.32,color=colors[cfg],label=label,zorder=3)
            for n,y in zip(x,heights):ax.text(n+offset,y+.8,f'{y:.2f}',ha='center',fontsize=10)
        ax.set_xticks(x,[f'Seed {s}' for s in seeds]);ax.set_ylim(0,limit)
        ax.set_ylabel(ylabel);ax.set_title(title,loc='left',pad=13)
        ax.grid(axis='y',color='#e2e8f0',zorder=0);ax.set_axisbelow(True)
    bars(axes[0,0],lambda c:[d['seeds'][s]['quality'][c]['all']['majority']['accurate'] for s in seeds],
         'A. Accuracy đa số trên test','Accuracy (%)',82)
    axes[0,0].legend(frameon=False,loc='upper left',ncol=2)
    ax=axes[0,1]
    for n,s in zip(x,seeds):
        r=d['seeds'][s]['paired_C1_vs_C0']['all']['primary_accurate']
        effect=r.get('diff_exact_pp',100*(r['up']-r['down'])/2156);lo,hi=r['ci95']
        ax.errorbar(effect,n,xerr=[[effect-lo],[hi-effect]],fmt='o',color=colors['C1'],capsize=5,lw=2)
        ax.text(hi+.15,n,f'{effect:+.2f} [{lo:.2f}; {hi:.2f}]',va='center',fontsize=10)
    ax.axvline(0,color='#94a3b8',lw=1,ls='--');ax.set_xlim(-.5,18)
    ax.set_yticks(x,[f'Seed {s}' for s in seeds]);ax.invert_yaxis();ax.set_ylim(2.7,-.7)
    ax.set_xlabel('B2 − C0 (điểm phần trăm)')
    ax.set_title('B. Hiệu số accuracy và CI95% ghép cặp',loc='left',pad=13)
    ax.grid(axis='x',color='#e2e8f0');ax.set_axisbelow(True)
    bars(axes[1,0],lambda c:[d['seeds'][s]['quality'][c]['null']['majority']['error'] for s in seeds],
         'C. Error trên 254 câu NULL','Error (%) — thấp hơn tốt hơn',50)
    for n,s in zip(x,seeds):
        r=d['seeds'][s]['paired_C1_vs_C0']['null']['secondary_error']
        ax0=axes[1,0];ax0.text(n,44,f"p = {r['p']:.3g}",ha='center',fontsize=10)
    bars(axes[1,1],lambda c:[d['seeds'][s]['evidence_recall'][c]['all']['micro_fact_recall_pct'] for s in seeds],
         'D. Evidence Recall của Sources thực tế','Micro fact recall (%)',52)
    fig.suptitle('MultiHop-RAG · C0 baseline và B2\nGemini V1 + amendment A1 · 2.156 câu · 3 seed sinh · 3 phiếu/đáp án',
                 fontsize=18,fontweight='bold',y=.98)
    fig.tight_layout(rect=(0,.085,1,.91),h_pad=3,w_pad=2)
    fig.text(.5,.025,'CI: bootstrap ghép cặp 10.000 mẫu, seed 13; p: exact McNemar hai phía.\n'
        'Ba phiếu chấm lại có JSON schema được công khai riêng. V1 strict gốc giữ nguyên 38.805 phiếu hợp lệ.',
        ha='center',fontsize=10,color='#475569')
    args.out.mkdir(parents=True,exist_ok=True)
    for ext in ('png','svg'):fig.savefig(args.out/f'MULTIHOP_PHASE3_C0_B2.{ext}',dpi=200,facecolor='white')
    plt.close(fig)
    print(json.dumps({'figure':str(args.out/'MULTIHOP_PHASE3_C0_B2.png')}))


if __name__=='__main__':main()

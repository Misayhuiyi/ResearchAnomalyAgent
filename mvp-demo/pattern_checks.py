"""Bounded, explicitly opted-in patterns. Never infer experimental pairing from a fit."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext
from itertools import combinations
import re

MAX_ROWS = 1000
MAX_COLUMNS = 20
MAX_PAIRS = 190
MAX_HITS = 200
MIN_PAIRS = 5
NAMES = {
    'DET-01a':'连续数值重复', 'DET-01b':'数值集合重合', 'DET-01c':'数据变化相似',
    'DET-02a':'固定差值', 'DET-02b':'固定倍数', 'DET-02c':'线性关系', 'DET-02d':'已知加权关系',
    'DET-03a':'小数变动后的重复', 'DET-03b':'十进制倍率关系', 'DET-03c':'重排后重复',
    'DET-04a':'舍入后重复', 'DET-04b':'报告精度不一致', 'DET-04c':'末位数字分布',
    'DET-08a':'时间轨迹重复', 'DET-08b':'时间轨迹固定关系', 'DET-08c':'局部时间轨迹重复',
    'DET-09a':'组成项与合计不一致', 'DET-09b':'连续机械序列', 'DET-09c':'分母与比例不一致',
}
MODES = {
    'vectors': {'ids': ['DET-01a','DET-01b','DET-01c','DET-02a','DET-02b','DET-02c','DET-03a','DET-03b','DET-03c','DET-04a','DET-04b','DET-04c'],
                'name':'数值关系与精度', 'assumption':'待比较数值列使用相同单位；逐行比较的观测已对齐，小数变换仅搜索1至3位。'},
    'weighted': {'ids':['DET-02d'], 'name':'已知加权关系', 'assumption':'输入、结果与权重属于同一行观测；材料已给出两个组成项的权重。'},
    'time': {'ids':['DET-08a','DET-08b','DET-08c'], 'name':'重复测量轨迹', 'assumption':'对象、时间和数值列表示同一指标、相同单位下的真实观测，不把插值当原始值。'},
    'sums': {'ids':['DET-09a'], 'name':'组成项合计', 'assumption':'组成项与合计属于同一口径，单位相同且已列出全部组成项。'},
    'sequence': {'ids':['DET-09b'], 'name':'有序数据规律', 'assumption':'顺序列明确声明观测顺序，数值为原始观测而不是按公式生成的设计值。'},
    'denominator': {'ids':['DET-09c'], 'name':'分母与比例', 'assumption':'每行分子、分母和比例属于同一口径，比例按0至1填写且未加权。'},
}


def check_table(filename, sheet, headers, rows, mode, parse):
    with localcontext() as context:
        context.prec=80
        return _check_table(filename,sheet,headers,rows,mode,parse)


def _check_table(filename, sheet, headers, rows, mode, parse):
    definition = MODES[mode]
    coverage = {key:{'rule_id':key,'name':NAMES[key],'file':filename,'sheet':sheet,'status':'insufficient',
                    'checked_rows':0,'skipped_rows':0,'findings_total':0,'findings_shown':0,'comparisons':0,
                    'assumption':definition['assumption'],'notes':[]} for key in definition['ids']}
    seen_rows = defaultdict(set)
    findings, dedupe = [], {}
    limited = len(rows)>MAX_ROWS or len(headers)>MAX_COLUMNS
    rows=rows[:MAX_ROWS]
    def tested(ids, indices):
        for key in ids:
            seen_rows[key].update(indices)
            coverage[key]['comparisons']+=1
    def point(row, index):
        if len(row['values'])!=len(headers):
            return None
        value=row['values'][index]
        try:
            raw=parse(value)
            formatted=parse(value, row['formats'][index]) if row.get('formats') else raw
        except ValueError:
            return None
        return {'file':filename,'sheet':sheet,'row_idx':row['row_idx'],'column':str(headers[index]),
                'value':formatted.original,'number':raw.value,'display_number':formatted.value,'quantum':formatted.quantum}
    def public(cell):
        return {key:cell[key] for key in ['file','sheet','row_idx','column','value']}
    def add(ids, summary, points, calculation=None, pairs=None, info=False):
        for key in ids:
            coverage[key]['findings_total']+=1
        signature=tuple(sorted((p['row_idx'],p['column']) for p in points))
        if signature in dedupe:
            prior=dedupe[signature]
            prior['rule_ids']=list(dict.fromkeys(prior['rule_ids']+ids))
            prior['matched_rules'].append({'rule_ids':ids,'summary':summary,'calculation':calculation or {}})
            for key in ids:
                coverage[key]['findings_shown']+=1
            return
        if len(findings)>=MAX_HITS:
            return
        selected=points[:100]
        evidence={'headers':['列名','原始值'],'rows':[{'row_idx':p['row_idx'],'values':[p['column'],p['value']]} for p in selected],
                  'highlight_cols':[2], 'note_cn':f'显示 {len(selected)} / {len(points)} 个原始值；数据关系需结合实验设计核对。'}
        if pairs:
            evidence['comparison']=[{'left':public(a),'right':public(b)} for a,b in pairs[:50]]
        record={'id':'','kind':'declared_pattern','rule_id':ids[0],'rule_ids':ids,'rule_version':'1.0',
                'category':'declared_patterns','severity':'info' if info else 'medium','file':filename,'sheet':sheet,
                'columns':list(dict.fromkeys(p['column'] for p in points)), 'n':len(pairs) if pairs else len(points),
                'location':f"{filename} · {sheet} · 第 {min(p['row_idx'] for p in points)} 至 {max(p['row_idx'] for p in points)} 行",
                'title_cn':NAMES[ids[0]],'summary_cn':summary,'rule':(calculation or {}).get('formula',NAMES[ids[0]]),
                'calculation':calculation or {},'matched_rules':[{'rule_ids':ids,'summary':summary,'calculation':calculation or {}}],
                'next_steps':['核对原始值、单位和对应观测。','已知换算、共享数据或派生公式可能解释该关系。'], 'evidence':evidence}
        findings.append(record); dedupe[signature]=record
        for key in ids:
            coverage[key]['findings_shown']+=1
    def column(name):
        choices=[i for i,h in enumerate(headers) if str(h).strip().lower()==name.lower()]
        if len(choices)!=1:
            raise ValueError('所需列缺失或重复，未推测字段对应')
        return choices[0]
    def bounds(cell):
        if cell['quantum'] is None:
            raise ValueError('显示精度不明，无法比较报告舍入区间')
        return cell['display_number']-cell['quantum']/2, cell['display_number']+cell['quantum']/2
    def overlap(a,b):
        return a[0]<=b[1] and b[0]<=a[1]
    def relation(a,b):
        x=[p['number'] for p in a]; y=[p['number'] for p in b]
        if len(a)<MIN_PAIRS or len(set(x))<2 or len(set(y))<2:
            return {}
        result={}
        differences={v-u for u,v in zip(x,y)}
        if len(differences)==1:
            result['offset']=next(iter(differences))
        if all(x):
            ratio=y[0]/x[0]
            if ratio and all(v*x[0]==u*y[0] for u,v in zip(x,y)):
                result['ratio']=ratio
        j=next(i for i,v in enumerate(x) if v!=x[0])
        dx,dy=x[j]-x[0],y[j]-y[0]
        if all((v-y[0])*dx==(u-x[0])*dy for u,v in zip(x,y)):
            slope=dy/dx; result['linear']=(slope,y[0]-slope*x[0])
        return result
    def contiguous(a,b):
        # Fixed 5-point hashes and at most three starts per hash bound duplicate-heavy searches.
        starts=defaultdict(list)
        for j in range(len(b)-MIN_PAIRS+1):
            if all(b[j:j+MIN_PAIRS]):
                key=tuple(p['number'] for p in b[j:j+MIN_PAIRS])
                if len(starts[key])<3:
                    starts[key].append(j)
                elif '每段相同的5点组合最多检查3个起点；仅保留最长连续匹配。' not in coverage['DET-01a']['notes']:
                    coverage['DET-01a']['notes'].append('每段相同的5点组合最多检查3个起点；仅保留最长连续匹配。')
        best=[]
        for i in range(len(a)-MIN_PAIRS+1):
            if len(a)-i<=len(best):
                break
            if not all(a[i:i+MIN_PAIRS]):
                continue
            key=tuple(p['number'] for p in a[i:i+MIN_PAIRS])
            if len(set(key))<2:
                continue
            for j in starts.get(key,[]):
                if min(len(a)-i,len(b)-j)<=len(best):
                    continue
                k=0
                while i+k<len(a) and j+k<len(b) and a[i+k] and b[j+k] and a[i+k]['number']==b[j+k]['number']:
                    k+=1
                if k>len(best):
                    best=list(zip(a[i:i+k],b[j:j+k]))
        return best
    try:
        if len(set(str(h).strip().lower() for h in headers))!=len(headers):
            raise ValueError('列名重复，无法唯一定位原始数值')
        if mode=='vectors':
            vectors=[]
            for index in range(min(len(headers),MAX_COLUMNS)):
                cells=[point(row,index) for row in rows]
                valid=[p for p in cells if p]
                if not valid:
                    continue
                vectors.append(cells)
                if len(valid)<len(cells):
                    for item in coverage.values():
                        item['skipped_rows']=max(item['skipped_rows'],len(cells)-len(valid))
                if len(valid)>=MIN_PAIRS:
                    precise=[p for p in valid if p['quantum'] is not None]
                    if len(precise)==len(valid):
                        tested(['DET-04a','DET-04b'],[p['row_idx'] for p in valid])
                        precision=Counter(str(p['quantum']) for p in valid)
                        if len(precision)>1:
                            add(['DET-04b'],'同列数值的报告小数位不一致，请核对记录方式。',valid,{'precision_counts':dict(precision)},info=True)
                        for digits in [1,2,3]:
                            groups=defaultdict(list)
                            for p in valid:
                                groups[p['number'].quantize(Decimal(1).scaleb(-digits),rounding=ROUND_HALF_UP)].append(p)
                            for rounded,group in groups.items():
                                if len(group)>1 and len({p['number'] for p in group})>1:
                                    add(['DET-04a'],f'{len(group)} 个不同原值保留 {digits} 位小数后均为 {rounded}。',group,{'digits':digits,'rounded':str(rounded)},info=True)
                    if len(valid)>=8 and len(precise)==len(valid):
                        tested(['DET-04c'],[p['row_idx'] for p in valid])
                        # Frequency is descriptive without a material-supported null distribution.
                        digits=[str(abs(p['number']).quantize(p['quantum'])).replace('.','')[-1] for p in valid]
                        counts=Counter(digits); longest=run=1
                        for i in range(1,len(digits)):
                            run=run+1 if digits[i]==digits[i-1] and valid[i]['row_idx']==valid[i-1]['row_idx']+1 else 1
                            longest=max(longest,run)
                        add(['DET-04c'],'末位数字频数：'+ '、'.join(f'{k} 出现 {v} 次' for k,v in sorted(counts.items()))+f'；相同末位最长连续 {longest} 行；无测量分布依据，不判断显著性。',valid,{'counts':dict(counts),'longest_equal_tail_run':longest,'denominator':len(valid)},info=True)
            for pair_index,(a,b) in enumerate(combinations(vectors,2)):
                if pair_index>=MAX_PAIRS:
                    limited=True;break
                if sum(p is not None for p in a)>=MIN_PAIRS and sum(p is not None for p in b)>=MIN_PAIRS:
                    tested(['DET-01a'],[p['row_idx'] for p in a+b if p])
                matches=contiguous(a,b)
                if matches:
                    add(['DET-01a'],f'发现连续 {len(matches)} 组相同数值，保留两侧原始位置。',[p for pair in matches for p in pair],{'matched':len(matches),'denominator':min(len(a),len(b))},matches)
                if not all(a+b) or len(a)<MIN_PAIRS or len(set(p['number'] for p in a))<2 or len(set(p['number'] for p in b))<2:
                    continue
                tested(['DET-01b','DET-03c','DET-02a','DET-02c','DET-01c','DET-03a'],[p['row_idx'] for p in a+b])
                x=[p['number'] for p in a]; y=[p['number'] for p in b]
                cx,cy=Counter(x),Counter(y);common=sum((cx&cy).values())
                if Decimal(common)/max(len(x),len(y))>=Decimal('.8'):
                    ids=['DET-01b']; pairs=None
                    text=f'忽略顺序后，{common} / {max(len(x),len(y))} 个数值重合，保留重复次数；不据此推断实验对象。'
                    if cx==cy and x!=y:
                        ids.append('DET-03c')
                        if len(cx)==len(x):
                            target={p['number']:p for p in b};pairs=[(p,target[p['number']]) for p in a]
                        else:
                            text+=' 重复值导致位置对应不唯一，仅列集合证据。'
                    add(ids,text,a+b,{'matched':common,'denominator':max(len(x),len(y))},pairs)
                rel=relation(a,b); pairs=list(zip(a,b))
                if 'offset' in rel and rel['offset']:
                    add(['DET-02a'],f"逐行数值保持固定差值 {rel['offset']}。",a+b,{'formula':f"第二列 = 第一列 + {rel['offset']}",'matched':len(a),'denominator':len(a)},pairs)
                if all(x):
                    tested(['DET-02b','DET-03b'],[p['row_idx'] for p in a+b])
                    if 'ratio' in rel and rel['ratio']!=1:
                        ids=['DET-02b']
                        if rel['ratio'] in {Decimal(10)**k for k in range(-6,7) if k}:
                            ids.append('DET-03b')
                        add(ids,f"逐行数值保持固定倍数 {rel['ratio']}。",a+b,{'formula':f"第二列 = 第一列 × {rel['ratio']}",'matched':len(a),'denominator':len(a)},pairs)
                if 'linear' in rel:
                    slope,offset=rel['linear']
                    add(['DET-02c'],f'两列满足线性关系：第二列 = {slope} × 第一列 + {offset}；拟合不证明数据生成方式。',a+b,{'slope':str(slope),'intercept':str(offset),'max_residual':'0','matched':len(a),'denominator':len(a)},pairs)
                xmean=sum(x)/len(x); ymean=sum(y)/len(y)
                xx=sum((v-xmean)**2 for v in x); yy=sum((v-ymean)**2 for v in y)
                xy=sum((u-xmean)*(v-ymean) for u,v in zip(x,y));slope=xy/xx
                residual=max(abs(v-(ymean+slope*(u-xmean))) for u,v in zip(x,y))
                correlation=xy/(xx*yy).sqrt()
                if abs(correlation)>=Decimal('.98') and residual/(max(y)-min(y))<=Decimal('.001'):
                    add(['DET-01c'],f'相关性约 {correlation:.4f}，线性拟合最大残差约 {residual:.6g}；相似程度仅作为辅助提示。',a+b,{'correlation':str(correlation),'max_residual':str(residual),'matched':len(a),'denominator':len(a)},pairs,True)
                if x!=y:
                    for digits in [1,2,3]:
                        quantum=Decimal(1).scaleb(-digits)
                        if all(u.quantize(quantum,rounding=ROUND_HALF_UP)==v.quantize(quantum,rounding=ROUND_HALF_UP) for u,v in zip(x,y)):
                            add(['DET-03a'],f'两列完整数值不同，但保留 {digits} 位小数后逐行相同。',a+b,{'digits':digits,'matched':len(a),'denominator':len(a)},pairs);break
        elif mode=='weighted':
            indices=[column(x) for x in ['输入1','输入2','权重1','权重2','结果']]
            values=[[point(row,i) for i in indices] for row in rows]
            if len(values)<MIN_PAIRS or not all(all(row) for row in values):
                raise ValueError('已知加权关系至少需要5行完整数据')
            tested(['DET-02d'],[row['row_idx'] for row in rows])
            if len({tuple(p['number'] for p in row[:2]) for row in values})<2:
                raise ValueError('恒定输入不验证加权关系')
            if all(row[0]['number']*row[2]['number']+row[1]['number']*row[3]['number']==row[4]['number'] for row in values):
                add(['DET-02d'],'结果与材料中给出的权重完全一致；已知派生公式可解释该关系。',[p for row in values for p in row],{'formula':'结果 = 输入1 × 权重1 + 输入2 × 权重2','matched':len(values),'denominator':len(values)},info=True)
        elif mode=='time':
            obj_i,time_i,val_i=[column(x) for x in ['对象','时间','数值']]
            tracks=defaultdict(dict)
            for row in rows:
                if len(row['values'])!=len(headers):
                    raise ValueError('时间轨迹存在缺列')
                obj='' if row['values'][obj_i] is None else str(row['values'][obj_i]).strip(); time=str(row['values'][time_i]).strip()
                p=point(row,val_i)
                if not obj or not time or not p:
                    raise ValueError('对象、时间或数值不完整')
                try:
                    stamp=('number',parse(time).value)
                except ValueError:
                    parsed_time=datetime.fromisoformat(time)
                    stamp=('utc',parsed_time.astimezone(timezone.utc).isoformat()) if parsed_time.tzinfo else ('local',parsed_time.isoformat())
                if stamp in tracks[obj]:
                    raise ValueError('同一对象有重复时间点，未自行去重')
                tracks[obj][stamp]=p
            if len(tracks)<2:
                raise ValueError('至少需要两个对象的轨迹')
            if len({time[0] for track in tracks.values() for time in track})!=1:
                raise ValueError('时间格式或时区口径不一致，未自行转换配对')
            for index,(a,b) in enumerate(combinations(tracks.values(),2)):
                if index>=MAX_PAIRS:
                    limited=True;break
                common=sorted(a.keys()&b.keys())
                if len(common)<MIN_PAIRS:
                    continue
                # No interpolation or row-index inference; local windows retain actual times.
                left,right=[a[t] for t in common],[b[t] for t in common]
                if a.keys()==b.keys():
                    tested(['DET-08a','DET-08b'],[p['row_idx'] for p in left+right])
                    rel=relation(left,right)
                    if 'offset' in rel and rel['offset']==0:
                        add(['DET-08a'],'相同实际时间点的两条轨迹完全相同。',left+right,{'time_points':[str(t[1]) for t in common]},list(zip(left,right)))
                    elif 'offset' in rel or 'ratio' in rel:
                        add(['DET-08b'],'按实际时间点对齐后，轨迹保持固定差值或倍数。',left+right,{'relations':{k:str(v) for k,v in rel.items()},'time_points':[str(t[1]) for t in common]},list(zip(left,right)))
                    elif len(common)>=MIN_PAIRS+1:
                        da=[{**p,'number':p['number']-left[i]['number']} for i,p in enumerate(left[1:])]
                        db=[{**p,'number':p['number']-right[i]['number']} for i,p in enumerate(right[1:])]
                        differences=relation(da,db)
                        if 'offset' in differences or 'ratio' in differences:
                            add(['DET-08b'],'按相同实际时间区间计算变化量后，两组变化量保持固定差值或倍数。',left+right,
                                {'formula':'相邻时间点变化量 = 后一原值 - 前一原值','relations':{k:str(v) for k,v in differences.items()},
                                 'time_points':[str(t[1]) for t in common],'left_differences':[str(p['number']) for p in da],
                                 'right_differences':[str(p['number']) for p in db]},list(zip(left,right)))
                tested(['DET-08c'],[p['row_idx'] for p in left+right])
                for start in range(len(common)-MIN_PAIRS+1):
                    times=common[start:start+MIN_PAIRS]
                    # A local window must also be contiguous in each original time axis.
                    if any(t not in times for t in a if times[0]<t<times[-1]) or any(t not in times for t in b if times[0]<t<times[-1]):
                        continue
                    aa,bb=left[start:start+MIN_PAIRS],right[start:start+MIN_PAIRS]
                    local_relation=relation(aa,bb)
                    if 'offset' in local_relation or 'ratio' in local_relation:
                        add(['DET-08c'],'连续的实际时间点出现重复、固定差值或倍数关系。',aa+bb,{'time_points':[str(t[1]) for t in times]},list(zip(aa,bb)));break
        elif mode=='sequence':
            order_i,value_i=column('顺序'),column('数值')
            ordered=[(point(row,order_i),point(row,value_i)) for row in rows]
            if len(ordered)<MIN_PAIRS or not all(a and b for a,b in ordered):
                raise ValueError('需要至少5行完整的顺序与数值')
            if len({a['number'] for a,b in ordered})!=len(ordered):
                raise ValueError('声明的顺序存在重复')
            ordered.sort(key=lambda item:item[0]['number']); points=[b for a,b in ordered]
            tested(['DET-09b'],[p['row_idx'] for p in points])
            values=[p['number'] for p in points]
            rel={}
            if len(set(values))>1:
                differences={b-a for a,b in zip(values,values[1:])}
                if len(differences)==1:
                    rel['offset']=next(iter(differences))
                if all(values[:-1]) and all(b*values[0]==a*values[1] for a,b in zip(values,values[1:])):
                    rel['ratio']=values[1]/values[0]
            if 'offset' in rel or 'ratio' in rel:
                add(['DET-09b'],'按材料声明的顺序排列后，数值构成等差或等比序列。',points,{'relations':{k:str(v) for k,v in rel.items()}})
        else:
            if mode=='sums':
                indices=[i for i,h in enumerate(headers) if re.fullmatch(r'组成([1-9]|1\d|20)',str(h).strip())]
                target=column('合计');key='DET-09a'
                if len(indices)<2 or len(set(str(headers[i]) for i in indices))!=len(indices):
                    raise ValueError('组成项缺少或重复，未推测合计口径')
            else:
                indices=[column('分子'),column('分母')];target=column('比例');key='DET-09c'
            for row in rows:
                points=[point(row,i) for i in indices+[target]]
                try:
                    if not all(points):
                        raise ValueError('该行缺少适用数值')
                    if mode=='sums':
                        ranges=[bounds(p) for p in points[:-1]]
                        expected=(sum(lo for lo,hi in ranges),sum(hi for lo,hi in ranges))
                        formula='合计 = 所有已列组成项之和'
                    else:
                        numerator,denominator=points[:-1]
                        if denominator['number']<=0:
                            raise ValueError('分母须大于0')
                        if not 0<=numerator['number']<=denominator['number'] or not 0<=points[-1]['number']<=1:
                            raise ValueError('分子须介于0与分母之间，比例须介于0与1之间')
                        # Declared numerator/denominator are exact, only reported ratio is rounded.
                        value=numerator['number']/denominator['number'];expected=(value,value)
                        formula='比例 = 分子 ÷ 分母'
                    reported=bounds(points[-1]);tested([key],[row['row_idx']])
                    if not overlap(expected,reported):
                        add([key],f'按{formula}复算，允许区间为 [{expected[0]}, {expected[1]}]，与材料中的 {points[-1]["value"]} 不一致。',points,{'formula':formula,'expected_interval':list(map(str,expected))})
                except ValueError as exc:
                    coverage[key]['skipped_rows']+=1
                    if str(exc) not in coverage[key]['notes']:
                        coverage[key]['notes'].append(str(exc))
    except (ValueError,ArithmeticError) as exc:
        for item in coverage.values():
            item['notes'].append(str(exc))
    for key,item in coverage.items():
        item['checked_rows']=len(seen_rows[key])
        if item['checked_rows']:
            item['status']='partial' if limited or item['notes'] or item['skipped_rows'] else 'checked'
        elif not item['notes']:
            item['notes'].append('缺少满足本项前提的完整数值、明确字段或足够观测。')
        if limited:
            item['notes'].append('扩展检查限前1000行、前20列与190组比较，本表范围未完整覆盖。')
        if item['findings_total']>item['findings_shown']:
            item['notes'].append('命中较多，仅展示本表前200项关系。')
    return findings,list(coverage.values())

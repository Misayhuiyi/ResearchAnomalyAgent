"""Registered read-only tools: model mappings are proposals, never numerical facts.

Every value and context label is verified against server-owned source text. Different
or ambiguous context is left unchecked. Unit conversion is a finite versioned list.
"""
from decimal import Decimal
import re

from statistical_checks import number, interval

TOOL_VERSION='1.0'
UNITS={
    'g':('mass',Decimal(1)), 'mg':('mass',Decimal('.001')), 'kg':('mass',Decimal(1000)),
    'µg':('mass',Decimal('.000001')), 'ug':('mass',Decimal('.000001')),
    'L':('volume',Decimal(1)), 'mL':('volume',Decimal('.001')),
    'mg/L':('concentration',Decimal(1)), 'µg/mL':('concentration',Decimal(1)),
    'g/L':('concentration',Decimal(1000)),
    '%':('proportion',Decimal('.01')), 'fraction':('proportion',Decimal(1)),
    'n':('count',Decimal(1)),
}
FIELDS=('metric','group','time','population')


class ToolError(ValueError):pass


def cite(catalog, item):
    if not isinstance(item,dict) or set(item)!={'source_id','quote'}:raise ToolError('引用格式不完整。')
    source=catalog.get(item['source_id']) if isinstance(item['source_id'],str) else None
    quote=item['quote']
    if not source or not isinstance(quote,str) or not quote.strip() or len(quote)>2000 or quote not in source['text']:
        raise ToolError('引用不能在本次材料中找到。')
    return {'source_id':item['source_id'],'file':source['file'],'location':source['location'],'quote':quote}


def claim(catalog,item):
    if not isinstance(item,dict) or set(item)!={'source_id','value_start','value_end','context','unit'}:
        raise ToolError('数值对应关系不完整。')
    source=catalog.get(item['source_id']) if isinstance(item['source_id'],str) else None
    if not source:raise ToolError('数值来源不属于本次材料。')
    start,end=item['value_start'],item['value_end']
    if type(start)is not int or type(end)is not int or not 0<=start<end<=len(source['text']):
        raise ToolError('原始数值位置无效。')
    if end-start>80:raise ToolError('原始数值范围无效。')
    literal=source['text'][start:end]
    # A proposal cannot select the 1 in 100, a mantissa without exponent, or a positive
    # suffix in a negative number. Delimiters are supplied by the actual source.
    numeric_neighbors=set('0123456789.+-eE')
    if (start and source['text'][start-1] in numeric_neighbors) or (end<len(source['text']) and source['text'][end] in numeric_neighbors):
        raise ToolError('引用未包含完整原始数值。')
    try: parsed=number(literal)
    except ValueError:raise ToolError('引用位置不是本版支持的单一数值。') from None
    context=item['context']
    if not isinstance(context,dict) or set(context)!=set(FIELDS):raise ToolError('指标、分组、时间或人群信息不足。')
    for label in context.values():
        if not isinstance(label,str) or not label.strip() or len(label)>200 or label not in source['text']:
            raise ToolError('对应条件缺少原文依据。')
    unit=item['unit']
    if (not isinstance(unit,str) or unit not in UNITS or
            not re.match(r'\s*'+re.escape(unit)+r'(?![A-Za-zµ])', source['text'][end:])):
        raise ToolError('单位缺少依据或暂不支持换算。')
    return {'source':source,'context':context,'unit':unit,'cell':parsed,'value_start':start,'value_end':end}


def compare_claims(catalog, args):
    if not isinstance(args,dict) or set(args)!={'left','right'}:raise ToolError('比较请求格式无效。')
    try:
        left,right=claim(catalog,args['left']),claim(catalog,args['right'])
        normal=lambda s:re.sub(r'\s+',' ',s.strip()).casefold()
        if any(normal(left['context'][field])!=normal(right['context'][field]) for field in FIELDS):
            raise ToolError('指标、分组、时间或人群不同，未自动合并比较。')
        if left['source']['location']==right['source']['location'] and args['left']['source_id']==args['right']['source_id']:
            raise ToolError('两侧引用来自同一处，未作为跨材料矛盾。')
        lunit,runit=UNITS[left['unit']],UNITS[right['unit']]
        if lunit[0]!=runit[0]:raise ToolError('单位量纲不同，不能直接比较。')
        lrange=tuple(v*lunit[1] for v in interval(left['cell'],None))
        rrange=tuple(v*runit[1] for v in interval(right['cell'],None))
        mismatch=lrange[1]<rrange[0] or rrange[1]<lrange[0]
        kinds={left['source']['kind'],right['source']['kind']}
        rules=[]
        if 'body' in kinds and 'table' in kinds:rules.append('DET-07a')
        if 'table' in kinds and 'supplement' in kinds:rules.append('DET-07b')
        if left['unit']!=right['unit']:rules.append('DET-07c')
        if not rules:raise ToolError('材料角色不满足本次正文、主表或补充表核对范围。')
        citations=[{'file':side['source']['file'],'location':side['source']['location'],
                    'original':side['cell'].original,'unit':side['unit'],
                    'context':side['context'],'value_start':side['value_start'],'value_end':side['value_end']}
                   for side in [left,right]]
        return {'status':'checked','rule_ids':rules,'mismatch':mismatch,'citations':citations,
                'mapping_status':'proposed_requires_review',
                'summary':'按提出的对应关系复算，两侧数值不一致；请确认指标和分组对应。' if mismatch else '按提出的对应关系，考虑单位换算及保留位数后数值相符；仍需确认对应口径。',
                'formula':f"左侧 × {lunit[1]} 与右侧 × {runit[1]} 比较舍入区间",
                'intervals':[list(map(str,lrange)),list(map(str,rrange))],'tool_version':TOOL_VERSION}
    except (ToolError,ValueError) as exc:
        return {'status':'insufficient','mismatch':None,'summary':str(exc),'tool_version':TOOL_VERSION}


def run_tool(catalog, name, args):
    if name=='compare_claims':return compare_claims(catalog,args)
    if name=='read_source':
        if not isinstance(args,dict) or set(args)!={'source_id'} or not isinstance(args['source_id'],str):
            raise ToolError('读取请求格式无效。')
        source=catalog.get(args['source_id'])
        if source is None:raise ToolError('来源不属于本次材料。')
        return source
    raise ToolError('该操作不在已登记的只读工具范围内。')


def validate_suggestions(catalog, result, finding_ids):
    """Do not persist raw model speech or accept model-generated review states."""
    if not isinstance(result,dict) or set(result)!={'suggestions','tool_requests'}:
        raise ToolError('论文复核响应格式无效。')
    suggestions=result['suggestions']; requests=result['tool_requests']
    if not isinstance(suggestions,list) or len(suggestions)>30 or not isinstance(requests,list) or len(requests)>20:
        raise ToolError('本次复核建议超出范围。')
    safe=[]
    allowed={'shared_control':'原文提到共享对照，可据此进一步核对。','derived_formula':'原文给出派生公式，可据此核对。',
             'unit_conversion':'原文给出单位信息，可据此核对换算。','needs_context':'现有材料不足以解释该项，需补充核对。'}
    for item in suggestions:
        if (not isinstance(item,dict) or set(item)!={'finding_id','reason','citations'} or
                not isinstance(item['finding_id'],str) or not isinstance(item['reason'],str) or
                item['finding_id'] not in finding_ids or item['reason'] not in allowed):
            raise ToolError('复核建议包含无效项目或未经允许的状态。')
        if not isinstance(item['citations'],list) or not 1<=len(item['citations'])<=5:raise ToolError('复核建议缺少出处。')
        citations=[cite(catalog,c) for c in item['citations']]
        words={'shared_control':['共享对照','共用对照','shared control'],
               'derived_formula':['公式','formula','calculated as','derived from'],
               'unit_conversion':['单位','unit','mg','µg','mL']}
        joined=' '.join(c['quote'] for c in citations).lower()
        if item['reason'] in words and not any(word.lower() in joined for word in words[item['reason']]):
            raise ToolError('所引原文未包含该解释所需信息，仍需人工核对。')
        safe.append({'finding_id':item['finding_id'],'summary':allowed[item['reason']],
                     'citations':citations, 'status':'suggestion_only'})
    outputs=[]
    for request in requests:
        if not isinstance(request,dict) or set(request)!={'name','arguments'}:raise ToolError('工具请求格式无效。')
        outputs.append(run_tool(catalog,request['name'],request['arguments']))
    return {'suggestions':safe,'tool_results':outputs,'tool_version':TOOL_VERSION}

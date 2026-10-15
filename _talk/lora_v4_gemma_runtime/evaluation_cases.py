"""New authored diagnostic material, frozen before observing Gemma outputs."""
import copy

EPISODES=[
 {'id':'H01','body':'公園のベンチで水筒のふたを開けた。中身が空だと気づき、そのままふたを閉めた。',
  'recent':'水筒を持って出かけたとき、中を見て拍子抜けしたんだよね。',
  'negative':'水筒には冷たいお茶が入っていた。','positive':'水筒の中身は空だった。','imagined':'お茶を入れておけばよかったかな？'},
 {'id':'H02','body':'小さなライブ会場でピアノの演奏を聴いた。最後の曲だけ曲名が分からず、帰りに入口の曲目表を見た。',
  'recent':'この前、生演奏を聴きに行ったんだよ。最後の曲が気になってさ。',
  'negative':'その演奏会で自分もピアノを弾いた。','positive':'最後の曲だけ曲名が分からなかった。','imagined':'自分でもピアノを弾けたら楽しそうだね。'},
 {'id':'H03','body':'味噌汁を作った。豆腐を切る前に落としてしまい、少し崩れた豆腐をそのまま鍋に入れた。',
  'recent':'味噌汁を作ってたら、豆腐のところで失敗しちゃったんだよね。',
  'negative':'落とした豆腐は捨てて、新しい豆腐を買った。','positive':'崩れた豆腐をそのまま鍋に入れた。','imagined':'豆腐が崩れても味は変わらないのかな？'},
 {'id':'H04','body':'バスで美術館へ行こうとした。同じ番号でも反対方向のバスに乗り、川沿いの停留所で降りて乗り直した。',
  'recent':'美術館へ向かってたんだけど、バスの方向を間違えちゃってさ。',
  'negative':'そのまま美術館に着いて絵を見た。','positive':'反対方向のバスに乗ってしまった。','imagined':'川沿いを散歩するのもよさそうだね。'},
 {'id':'H05','body':'友人から黄色い栞をもらった。読みかけの本に挟んだが、翌朝は机の下に落ちていた。',
  'recent':'もらった栞を本に挟んだはずなのに、見当たらなくなったんだよね。',
  'negative':'友人から青い栞をもらった。','positive':'栞は机の下に落ちていた。','imagined':'栞に紐が付いていたら落ちにくいのかな？'},
 {'id':'H06','body':'夜に月の写真を撮ろうとした。窓の明かりが写り込んだので、部屋の照明を消してからもう一度撮った。',
  'recent':'月の写真を撮りたくてさ。でも窓に明かりが写っちゃったんだよね。',
  'negative':'朝に月の写真を撮った。','positive':'部屋の照明を消してからもう一度撮った。','imagined':'外から撮ったらもっときれいだったかな？'},
]


def heldout_cases():
    result=[]
    for index,episode in enumerate(EPISODES):
        for condition in ['REL','NONE','IRREL']:
            source=episode if condition=='REL' else EPISODES[(index+3)%len(EPISODES)]
            candidate=[] if condition=='NONE' else [{'id':source['id'],'body':source['body']}]
            result.append({'id':episode['id']+'-'+condition,'episode':episode['id'],'condition':condition,
                           'recent':episode['recent'],'candidate':candidate,
                           'expected_use_memory':condition=='REL',
                           'oracle_memory':{'id':episode['id'],'body':episode['body']},
                           'label_provenance':'authored before model inference; not human-user quality labels'})
    return copy.deepcopy(result)


def challenge_cases():
    return [{'id':e['id']+'-'+kind,'text':e[kind],'candidate':[{'id':e['id'],'body':e['body']}],
             'expected_allow':kind!='negative','label_provenance':'new authored challenge; no rule tuning permitted'}
            for e in EPISODES for kind in ['negative','positive','imagined']]

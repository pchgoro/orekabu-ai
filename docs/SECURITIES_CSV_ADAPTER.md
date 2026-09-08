# 証券会社CSV adapterの現状境界

現時点の無料adapterは楽天証券MarketSpeed形式を対象に、UTF-8 BOM / UTF-8 / CP932の判定、ticker正規化、口座別保有数量の集約、preview、既存銘柄との比較を行います。

安全境界:

- 必須列不足・不正ticker・不正数量は行単位でfail-closedし、他の正常行を継続する。
- preview/parseはDBを書き換えない。
- 既存銘柄の更新は明示したpolicyのときだけ行う。
- CSVにない既存保有銘柄を自動で非保有へ変更しない。
- ユーザーメモ、買い検討価格、企業情報、キーワードを保全する。
- 実CSV未提供のSBI/Rakuten別形式を推測して対応しない。

実データ反映と証券会社別の正式な列仕様は、人間が実CSVを提供・確認した後のAcceptance対象です。

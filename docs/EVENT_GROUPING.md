# 同一材料の表示統合境界

`services.event_grouping.group_material_records` は、RSS・企業IR・適時開示・EDINETなどの既存レコードを削除・更新せず、表示用に決定論的なグループへ束ねる純粋なview modelです。

優先キーは `ticker + title + 日付` です。日付が揃わない場合だけ正規化URLへフォールバックします。各グループは元レコード全件と `provenance`（source、URL、record_id）を保持します。

この段階ではDB migration、既存行の統合、外部取得、通知送信を行いません。曖昧なタイトルや日付のないレコードは自動確定せず、後続の確認対象として扱います。

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
import pytest
from psnself import db, db_gamestats
from psnself.sync.trophy_sync import _find_ts_stats, _update_ts_stats
from psnself.sync.extractor import _normalize_name

FIRST = datetime(2024,8,8,17,18,47,tzinfo=timezone.utc)
LAST = datetime(2024,8,13,9,23,50,tzinfo=timezone.utc)
def stats(name='Example: Special Edition',seconds=0,title_id='PPSA1',count=1,first=FIRST,last=LAST):
    return NS(name=name,title_id=title_id,play_duration=timedelta(seconds=seconds) if seconds is not None else None,play_count=count,first_played_date_time=first,last_played_date_time=last)
def seed(conn, seconds=1800, title_id=None):
    db.upsert_game(conn,{'np_communication_id':'NP1','title_name':'Example','platform':'PS5'})
    conn.execute('INSERT INTO game_stats(np_communication_id,title_id,total_seconds) VALUES(?,?,?)',('NP1',title_id,seconds))
def match(conn,name,records,api_id=None):
    return _find_ts_stats(conn,NS(title_name=name,np_title_id=api_id),'NP1',{s.title_id:s for s in records},{_normalize_name(s.name):s for s in records})

@pytest.mark.parametrize('title,api_name',[('Sea of Stars','Sea of Stars: Sunset Edition'),('Example','Example: Special Edition'),('Example: Special Edition','Example'),('Example','Example : Special Edition')])
def test_colon_suffix_match(conn,title,api_name):
    s=stats(api_name);assert match(conn,title,[s]) is s

def test_id_and_exact_name_still_take_priority(conn):
    a,b=stats('Example',title_id='A'),stats('Example: Special Edition',title_id='B')
    assert match(conn,'Example',[a,b]) is a
    assert match(conn,'Example',[a,b],api_id='B') is b

def test_multiple_edition_candidates_are_ambiguous(conn):
    assert match(conn,'Example',[stats('Example: Special Edition',title_id='A'),stats('Example: Other Edition',title_id='B')]) is None

def test_partial_word_does_not_match(conn):
    assert match(conn,'Example',[stats('Examples: Special Edition')]) is None

@pytest.mark.parametrize('duration',[0,None])
def test_manual_time_survives_repeated_syncs_while_dates_and_count_update(conn,duration):
    seed(conn)
    for _ in range(3):_update_ts_stats(conn,'NP1',stats(seconds=duration))
    got=db_gamestats.get_game_stats(conn,'NP1')
    assert got['total_seconds']==1800 and got['title_id'] is None
    assert got['play_count']==1 and got['first_played']==FIRST.isoformat() and got['last_played']==LAST.isoformat()
    assert conn.execute('SELECT np_title_id FROM games WHERE np_communication_id="NP1"').fetchone()[0]=='PPSA1'
    assert conn.execute('SELECT COUNT(*) FROM play_delta_history').fetchone()[0]==0

def test_positive_duration_updates_normally_and_history_is_idempotent(conn):
    seed(conn,seconds=60840)
    _update_ts_stats(conn,'NP1',stats(seconds=60870,count=16))
    _update_ts_stats(conn,'NP1',stats(seconds=60870,count=16))
    got=db_gamestats.get_game_stats(conn,'NP1');assert got['total_seconds']==60870 and got['title_id']=='PPSA1' and got['play_count']==16
    assert [tuple(r) for r in conn.execute('SELECT date,delta_seconds FROM play_delta_history')]==[('2024-08-13',30)]

def test_missing_dates_and_count_keep_known_values(conn):
    seed(conn)
    _update_ts_stats(conn,'NP1',stats())
    _update_ts_stats(conn,'NP1',stats(seconds=None,count=None,first=None,last=None))
    got=db_gamestats.get_game_stats(conn,'NP1')
    assert got['first_played']==FIRST.isoformat() and got['last_played']==LAST.isoformat() and got['play_count']==1

def test_zero_does_not_erase_previously_synced_positive_time(conn):
    seed(conn,seconds=500,title_id='PPSA1')
    _update_ts_stats(conn,'NP1',stats(seconds=0))
    got=db_gamestats.get_game_stats(conn,'NP1');assert got['total_seconds']==500 and got['title_id']=='PPSA1'

def test_new_zero_duration_record_still_gets_dates(conn):
    db.upsert_game(conn,{'np_communication_id':'NP1','title_name':'Example','platform':'PS5'})
    _update_ts_stats(conn,'NP1',stats(seconds=0))
    got=db_gamestats.get_game_stats(conn,'NP1');assert got['total_seconds']==0 and got['first_played']==FIRST.isoformat()

from unittest.mock import Mock
from psnself.sync.trophy_sync import _resolve_unmatched_stats

def resolver(conn, records, replies, titles=None):
    client=Mock()
    client.get.side_effect=[NS(json=lambda reply=reply: reply) if isinstance(reply,dict) else reply for reply in replies]
    found=_resolve_unmatched_stats(conn,titles or [NS(title_name='Unrelated trophy name',np_title_id=None,np_communication_id='NP1')],{s.title_id:s for s in records},{_normalize_name(s.name):s for s in records},client)
    return found,client

def mapped(tid,comm='NP1'):
    return {'npTitleId':tid,'trophyTitles':[{'npCommunicationId':comm}]}

def test_sony_ids_resolve_completely_different_names(conn):
    s=stats('Different published name')
    found,client=resolver(conn,[s],[{'titles':[mapped(s.title_id)]}])
    assert found=={'NP1':s}
    assert '/users/me/' in client.get.call_args.kwargs['url']
    seed(conn)
    _update_ts_stats(conn,'NP1',found['NP1'])
    assert match(conn,'Unrelated trophy name',[s]) is s

def test_sony_mapping_batches_and_rejects_ambiguity_across_batches(conn):
    records=[stats('Other '+str(i),title_id='ID'+str(i)) for i in range(6)]
    found,client=resolver(conn,records,[{'titles':[mapped('ID0')]},{'titles':[mapped('ID5')]}])
    assert found=={} and client.get.call_count==2
    assert [len(c.kwargs['params']['npTitleIds'].split(',')) for c in client.get.call_args_list]==[5,1]

def test_sony_mapping_failure_discards_partial_result(conn):
    records=[stats('Other '+str(i),title_id='ID'+str(i)) for i in range(6)]
    found,_=resolver(conn,records,[{'titles':[mapped('ID0')]},RuntimeError('private')])
    assert found=={}

def test_sony_mapping_ignores_unrequested_ids_and_unknown_trophies(conn):
    found,_=resolver(conn,[stats('Other')],[{'titles':[mapped('UNREQUESTED'),mapped('PPSA1','OTHER')]}])
    assert found=={}

def test_sony_mapping_does_not_request_when_all_titles_match(conn):
    s=stats('Example')
    found,client=resolver(conn,[s],[],titles=[NS(title_name='Example',np_title_id=None,np_communication_id='NP1')])
    assert found=={} and not client.get.called

def test_sony_mapping_excludes_already_used_stats(conn):
    a,b=stats('Matched',title_id='A'),stats('Unmatched',title_id='B')
    titles=[NS(title_name='Matched',np_title_id=None,np_communication_id='NP2'),NS(title_name='Other',np_title_id=None,np_communication_id='NP1')]
    found,client=resolver(conn,[a,b],[{'titles':[mapped('B')]}],titles=titles)
    assert found=={'NP1':b} and client.get.call_args.kwargs['params']=={'npTitleIds':'B'}

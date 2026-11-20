"""Compact common-queue history and administrative audit presentation."""
from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository
from xti.application.job_history import JobHistoryService
from xti.interfaces.text import safe_text, xti_command


def make_job_history_service(data_dir):
    return JobHistoryService(SQLiteEngineJobRepository(data_dir / 'engine-jobs.sqlite3'))


def history_lines(data, *, data_dir=None):
    if 'items' in data:
        lines = ['İş geçmişi: ' + data['bucket']]
        for item in data['items']:
            lines.append(f"{safe_text(item['job_id'])} | {safe_text(item['job_kind'])} | "
                         f"{safe_text(item['status'])} | {safe_text(item['finished_at'] or item['created_at'])}")
        if not data['items']:
            lines.append('Bu pencerede kayıtlı iş yok.')
        if data['has_more']:
            lines.append('Sonraki sayfa: ' + xti_command('source-jobs', 'history', '--bucket', data['bucket'],
                '--limit', str(data['limit']), '--before-sequence', str(data['next_before_sequence']),
                '--expected-snapshot', data['snapshot_id'], data_dir=data_dir))
        return lines
    lines = ['Kuyruk denetimi başarılı.' if data.get('state') == 'verified' else 'Ortak motor kuyruğu']
    if data['schema_version'] < 4:
        return lines + [f"Eski kuyruk şeması: {data['schema_version']}; saklı iş: {data['retained_jobs']}.",
                        'Etkin işleri geçmişten ayırmak için source-jobs migrate çalıştırın.']
    return lines + [f"Etkin: {data['active_jobs']} / {data['active_limit']} | Arşiv: {data['archived_jobs']}",
        'Tamamlanan işler özgün sonuçları ve tekrar anahtarlarıyla aynı veritabanında korunur.',
        'Arşiv diskten silinmez; boyutu ayrıca izleyin.']

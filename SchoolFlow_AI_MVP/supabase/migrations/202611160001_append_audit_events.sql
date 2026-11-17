create or replace function public.append_audit_events(
    p_school_id uuid,
    p_events jsonb
)
returns void
language plpgsql
security definer
set search_path = pg_catalog, pg_temp
as $$
begin
    if p_school_id is null or not public.is_school_member(p_school_id) then
        raise exception 'Active school membership required to create audit events'
            using errcode = '42501';
    end if;

    if p_events is null or jsonb_typeof(p_events) <> 'array' then
        raise exception 'Audit events must be a JSON array'
            using errcode = '22023';
    end if;

    insert into public.audit_events (
        school_id, event_id, action, status, entity_type, occurred_at, record_data
    )
    select p_school_id, event.event_id, event.action, event.status,
           event.entity_type, event.occurred_at, event.record_data
    from jsonb_to_recordset(p_events) as event(
        event_id text,
        action text,
        status text,
        entity_type text,
        occurred_at timestamptz,
        record_data jsonb
    )
    on conflict (school_id, event_id) do nothing;
end;
$$;

revoke all on function public.append_audit_events(uuid, jsonb) from public, anon;
grant execute on function public.append_audit_events(uuid, jsonb) to authenticated;

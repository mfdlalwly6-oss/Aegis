from tests.conftest import OWNER_HEADERS, create_tenant


def test_csv_import_is_scoped_deduplicated_and_safe(client):
    tenant = create_tenant(client, name="Import Tenant")
    payload = b"list_type,value,source\nsanctions,zz,unit\nsanctions, ZZ ,unit\nbad,nope,x\n"
    r = client.post(
        f"/api/v1/admin/tenants/{tenant['tenant_id']}/watchlist/import",
        files={"file": ("watch.csv", payload, "text/csv")}, headers=OWNER_HEADERS,
    )
    assert r.status_code == 200
    assert r.json() == {"total_rows": 3, "imported_rows": 1, "skipped_rows": 1, "duplicate_rows": 1}
    assert client.app.state.registry.watchlist_repo.check("sanctions", "ZZ", tenant["tenant_id"])


def test_import_rejects_missing_required_columns(client):
    tenant = create_tenant(client, name="Columns Tenant")
    r = client.post(f"/api/v1/admin/tenants/{tenant['tenant_id']}/watchlist/import", files={"file": ("x.csv", b"name\na\n", "text/csv")}, headers=OWNER_HEADERS)
    assert r.status_code == 422

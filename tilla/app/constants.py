from app.models import InvoiceStatus

INVOICE_STATUS_LABELS_CS = {
    InvoiceStatus.NEW.value: "Nová",
    InvoiceStatus.PENDING_CHECK.value: "Čeká na kontrolu",
    InvoiceStatus.PENDING_DEBTOR_CONFIRM.value: "Čeká na potvrzení odběratele",
    InvoiceStatus.DEBTOR_CONFIRMED.value: "Potvrzená odběratelem",
    InvoiceStatus.PURCHASED.value: "Odkoupená",
    InvoiceStatus.ADVANCE_FINANCED.value: "Záloha profinancována",
    InvoiceStatus.AWAITING_COLLECTION.value: "Čeká na inkaso",
    InvoiceStatus.PARTIALLY_PAID.value: "Částečně uhrazená",
    InvoiceStatus.FULLY_SETTLED.value: "Plně vypořádaná",
    InvoiceStatus.OVERDUE.value: "Po splatnosti",
    InvoiceStatus.PROBLEM.value: "Problémová",
}

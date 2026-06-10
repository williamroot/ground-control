# znuny/scripts/ensure-automation-invoker.pl
# --
# Motor de automação (#1Q). Garante, de forma IDEMPOTENTE, que:
#   1) o Event module GertiAutomation está registrado (vem do XML SysConfig
#      bakeado em Custom/Kernel/Config/Files/XML/GertiAutomation.xml) — basta
#      reconstruir a config p/ o Znuny enxergar a Setting;
#   2) o segredo HMAC compartilhado (GertiAutomation::WebhookSecret) está setado
#      (renderizado pelo entrypoint a partir de GERTI_WEBHOOK_SIGNING_SECRET) —
#      caso contrário avisa (fail-closed: sem segredo, o módulo não posta).
#
# Sem passos destrutivos. Roda como otrs no provisionamento (entrypoint) e/ou no
# deploy. Espelha o estilo de ensure-gerti-dynamicfield.pl.
use strict;
use warnings;
use lib '/opt/otrs';
use lib '/opt/otrs/Kernel/cpan-lib';
use lib '/opt/otrs/Custom';
use Kernel::System::ObjectManager;

local $Kernel::OM = Kernel::System::ObjectManager->new();

my $ConfigObject = $Kernel::OM->Get('Kernel::Config');
my $SysConfig    = $Kernel::OM->Get('Kernel::System::SysConfig');

# 1) Reconstrói a config efetiva: a Setting Ticket::EventModulePost###9700-
#    GertiAutomation vem do XML (declarativo). ConfigurationDeploy é idempotente.
my %Deploy = $SysConfig->ConfigurationDeploy(
    Comments      => 'Gerti #1Q — ensure GertiAutomation event module',
    UserID        => 1,
    Force         => 1,
    DirtySettings => [],
);
if ( $Deploy{Success} ) {
    print "SysConfig deployed — GertiAutomation event module active.\n";
}
else {
    print "WARN: ConfigurationDeploy did not report success (may be a no-op).\n";
}

# 2) Verifica o segredo compartilhado (não imprime o valor).
my $Secret = $ConfigObject->Get('GertiAutomation::WebhookSecret');
if ( defined $Secret && $Secret ne '' ) {
    print "GertiAutomation::WebhookSecret is set (HMAC ready).\n";
}
else {
    print "WARN: GertiAutomation::WebhookSecret is EMPTY — set GERTI_WEBHOOK_SIGNING_SECRET "
        . "in .env.prod (same value as the sidecar). Until then NO events are posted (fail-closed).\n";
}

my $Url = $ConfigObject->Get('GertiAutomation::SidecarUrl') || '(default)';
print "GertiAutomation::SidecarUrl = $Url\n";

exit 0;

# znuny/Custom/Kernel/System/Ticket/Event/GertiAutomation.pm
# --
# Gerti — motor de automação (#1Q). Event module disparado em eventos de ticket
# (TicketCreate/ArticleCreate/TicketStateUpdate/TicketPriorityUpdate/
# TicketQueueUpdate/Escalation*TimeStart). Monta a payload canônica, assina
# HMAC-SHA256 com o segredo COMPARTILHADO (GertiAutomation::WebhookSecret) e faz
# POST ao sidecar (GertiAutomation::SidecarUrl). Best-effort: qualquer falha de
# rede é engolida (eval) — NUNCA quebra a transação do ticket no Znuny.
#
# Por que Event module (e não Invoker GI nativo): o Invoker não assina HMAC sobre
# o corpo exato; aqui controlamos byte-a-byte o corpo assinado. Spike R1Q.
# Upgrade-safe Custom/ overlay (primeiro no @INC).
# --
package Kernel::System::Ticket::Event::GertiAutomation;

use strict;
use warnings;

use Digest::SHA qw(hmac_sha256_hex);

our @ObjectDependencies = (
    'Kernel::Config',
    'Kernel::System::Ticket',
    'Kernel::System::JSON',
    'Kernel::System::WebUserAgent',
    'Kernel::System::Log',
);

# Znuny event name → trigger normalizado do sidecar.
my %EVENT_MAP = (
    TicketCreate                  => 'ticket_create',
    ArticleCreate                 => 'article_create',
    TicketStateUpdate             => 'state_update',
    TicketPriorityUpdate          => 'state_update',
    TicketQueueUpdate             => 'state_update',
    EscalationResponseTimeStart   => 'escalation',
    EscalationUpdateTimeStart     => 'escalation',
    EscalationSolutionTimeStart   => 'escalation',
);

sub new {
    my ( $Type, %Param ) = @_;
    my $Self = {};
    bless( $Self, $Type );
    return $Self;
}

sub Run {
    my ( $Self, %Param ) = @_;

    my $ConfigObject = $Kernel::OM->Get('Kernel::Config');
    my $LogObject    = $Kernel::OM->Get('Kernel::System::Log');

    # Segredo ausente → fail-closed: nada é postado (nunca posta sem assinar).
    my $Secret = $ConfigObject->Get('GertiAutomation::WebhookSecret');
    return 1 if !defined $Secret || $Secret eq '';

    my $Url = $ConfigObject->Get('GertiAutomation::SidecarUrl');
    return 1 if !defined $Url || $Url eq '';

    my $EventName = $Param{Event} // '';
    my $Trigger   = $EVENT_MAP{$EventName};
    return 1 if !$Trigger;    # evento não mapeado → ignora

    my $TicketID = $Param{Data} && $Param{Data}->{TicketID};
    return 1 if !$TicketID;

    # Best-effort: tudo dentro de eval — nunca derruba a transação do ticket.
    eval {
        my $TicketObject = $Kernel::OM->Get('Kernel::System::Ticket');
        my %T = $TicketObject->TicketGet(
            TicketID => $TicketID,
            UserID   => 1,
        );
        return 1 if !%T;

        my $AgeMinutes = defined $T{Age} ? int( $T{Age} / 60 ) : 0;

        my %Payload = (
            event       => $Trigger,
            ticket_id   => $TicketID + 0,
            customer_id => $T{CustomerID}    // '',
            title       => $T{Title}         // '',
            state       => $T{State}         // '',
            priority    => $T{Priority}      // '',
            queue       => $T{Queue}         // '',
            service     => $T{Service}       // '',
            type        => $T{Type}          // '',
            age_minutes => $AgeMinutes,
            sla_state   => $Self->_SlaState( \%T ),
        );

        my $JSONObject = $Kernel::OM->Get('Kernel::System::JSON');
        my $Body       = $JSONObject->Encode( Data => \%Payload );

        # Assina o corpo EXATO que será enviado (mesmo $Body literal).
        my $Sig = hmac_sha256_hex( $Body, $Secret );

        my $UA = $Kernel::OM->Get('Kernel::System::WebUserAgent');
        $UA->{Timeout} = 5;
        $UA->Request(
            Type => 'POST',
            URL  => $Url,
            Data => $Body,
            Header => {
                'Content-Type'      => 'application/json',
                'X-Gerti-Signature' => "sha256=$Sig",
            },
        );
        1;
    } or do {
        my $Err = $@ || 'unknown';
        $LogObject->Log(
            Priority => 'notice',
            Message  => "GertiAutomation: post falhou (best-effort): $Err",
        );
    };

    return 1;
}

# Estado de SLA simplificado a partir do TicketGet (ok|warning|breached).
sub _SlaState {
    my ( $Self, $T ) = @_;
    return 'breached' if $T->{SolutionTimeEscalation} || $T->{EscalationSolutionTime} && $T->{EscalationSolutionTime} < 0;
    return 'warning'  if $T->{SolutionTimeNotification} || $T->{EscalationDestinationIn};
    return 'ok';
}

1;
